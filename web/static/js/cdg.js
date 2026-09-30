class CDGPlayer {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d");
    this.bufferCanvas = document.createElement("canvas");
    this.bufferCanvas.width = 300;
    this.bufferCanvas.height = 216;
    this.bufferContext = this.bufferCanvas.getContext("2d");
    this.audio = null;
    this.trackDuration = null;
    this.current = null;
    this.packets = [];
    this.palette = Array.from({ length: 16 }, (_, index) => this.indexToColor(index));
    this.backgroundColorIndex = 0;
    this.borderColorIndex = null;
    this.pixelColorIndices = new Uint8Array(this.bufferCanvas.width * this.bufferCanvas.height);
    this.nextPacketIndex = 0;
    this.loaded = false;
    this.syncFrame = null;
    this.pendingStartSync = false;
  }

  indexToColor(index) {
    const level = index * 17;
    return `rgb(${level}, ${level}, ${level})`;
  }

  decodeColor(byte1, byte2) {
    const red = ((byte1 >> 2) & 0x0f) * 17;
    const green = (((byte1 & 0x03) << 2) | ((byte2 >> 4) & 0x03)) * 17;
    const blue = (byte2 & 0x0f) * 17;
    return `rgb(${red}, ${green}, ${blue})`;
  }

  bindAudio(audio) {
    this.audio = audio;
    if (!this.audio) {
      this.trackDuration = null;
      return;
    }
    const updateDuration = () => {
      const duration = this.audio?.duration;
      if (Number.isFinite(duration) && duration > 0) {
        this.trackDuration = duration;
      }
    };
    updateDuration();
    this.audio.addEventListener("loadedmetadata", updateDuration);
    this.audio.addEventListener("durationchange", updateDuration);
    this.audio.addEventListener("play", updateDuration);
  }

  async load(url, title = "", artist = "") {
    this.stop();
    this.current = { url, title, artist };
    this.drawPlaceholder(title || "Karaoke track", artist || "", "Loading lyrics...");
    const response = await fetch(url, { cache: "no-cache" });
    if (!response.ok) {
      this.drawPlaceholder(title || "Karaoke track", artist || "", "Unable to load CDG data");
      return;
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    this.packets = this.parsePackets(bytes);
    this.trackDuration = null;
    this.resetState();
    this.loaded = true;
    this.renderAt(this.audio ? this.audio.currentTime : 0);
  }

  parsePackets(bytes) {
    const packets = [];
    for (let offset = 0; offset + 23 < bytes.length; offset += 24) {
      packets.push(bytes.slice(offset, offset + 24));
    }
    return packets;
  }

  resetState() {
    this.palette = Array.from({ length: 16 }, (_, index) => this.indexToColor(index));
    this.backgroundColorIndex = 0;
    this.borderColorIndex = null;
    this.pixelColorIndices.fill(this.backgroundColorIndex);
    this.nextPacketIndex = 0;
    this.clearBuffer();
  }

  clearBuffer() {
    this.pixelColorIndices.fill(this.backgroundColorIndex);
    this.redrawFromIndices();
  }

  isBorderPixel(x, y) {
    return x < 6 || x >= this.bufferCanvas.width - 6 || y < 12 || y >= this.bufferCanvas.height - 12;
  }

  redrawFromIndices() {
    if (!this.bufferContext) {
      return;
    }
    this.bufferContext.clearRect(0, 0, this.bufferCanvas.width, this.bufferCanvas.height);
    for (let y = 0; y < this.bufferCanvas.height; y += 1) {
      for (let x = 0; x < this.bufferCanvas.width; x += 1) {
        const offset = x + y * this.bufferCanvas.width;
        const paletteIndex = this.borderColorIndex !== null && this.isBorderPixel(x, y)
          ? this.borderColorIndex
          : this.pixelColorIndices[offset];
        this.bufferContext.fillStyle = this.palette[paletteIndex] || this.indexToColor(paletteIndex);
        this.bufferContext.fillRect(x, y, 1, 1);
      }
    }
    this.blit();
  }

  loadColorTable(data, startIndex) {
    for (let index = 0; index < 8; index += 1) {
      const byte1 = data[index * 2];
      const byte2 = data[index * 2 + 1];
      this.palette[startIndex + index] = this.decodeColor(byte1, byte2);
    }
  }

  drawTile(data, xorMode) {
    if (!this.bufferContext) {
      return;
    }
    const color0Index = data[0] & 0x0f;
    const color1Index = data[1] & 0x0f;
    const row = data[2] & 0x1f;
    const column = data[3] & 0x3f;
    const x = column * 6;
    const y = row * 12;

    if (x + 6 > this.bufferCanvas.width || y + 12 > this.bufferCanvas.height) {
      return;
    }

    for (let line = 0; line < 12; line += 1) {
      const bits = data[4 + line];
      for (let pixel = 0; pixel < 6; pixel += 1) {
        const mask = 1 << (5 - pixel);
        const encodedColorIndex = bits & mask ? color1Index : color0Index;
        const px = x + pixel;
        const py = y + line;
        const offset = px + py * this.bufferCanvas.width;
        const paletteIndex = xorMode
          ? (this.pixelColorIndices[offset] ^ encodedColorIndex) & 0x0f
          : encodedColorIndex;
        this.pixelColorIndices[offset] = paletteIndex;

        const renderPaletteIndex = this.borderColorIndex !== null && this.isBorderPixel(px, py)
          ? this.borderColorIndex
          : paletteIndex;
        this.bufferContext.fillStyle = this.palette[renderPaletteIndex] || this.indexToColor(renderPaletteIndex);
        this.bufferContext.fillRect(px, py, 1, 1);
      }
    }
  }

  applyPacket(packet) {
    if ((packet[0] & 0x3f) !== 0x09) {
      return;
    }
    const op = packet[1] & 0x3f;
    const data = packet.subarray(4, 20);
    switch (op) {
      case 0x01:
        this.backgroundColorIndex = data[0] & 0x0f;
        this.borderColorIndex = null;
        this.clearBuffer();
        break;
      case 0x02:
        this.borderColorIndex = data[0] & 0x0f;
        this.redrawFromIndices();
        break;
      case 0x06:
        this.drawTile(data, false);
        this.blit();
        break;
      case 0x26:
        this.drawTile(data, true);
        this.blit();
        break;
      case 0x1e:
        this.loadColorTable(data, 0);
        this.redrawFromIndices();
        break;
      case 0x1f:
        this.loadColorTable(data, 8);
        this.redrawFromIndices();
        break;
      default:
        break;
    }
  }

  blit() {
    if (!this.context || !this.bufferCanvas) {
      return;
    }
    this.context.imageSmoothingEnabled = false;
    this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.context.drawImage(this.bufferCanvas, 0, 0, this.canvas.width, this.canvas.height);
  }

  getPacketRate() {
    return 300;
  }

  renderAt(timeSeconds) {
    if (!this.loaded) {
      return;
    }
    const targetPacket = Math.max(0, Math.floor(timeSeconds * this.getPacketRate()));
    while (this.nextPacketIndex < targetPacket && this.nextPacketIndex < this.packets.length) {
      this.applyPacket(this.packets[this.nextPacketIndex]);
      this.nextPacketIndex += 1;
    }
  }

  startSync() {
    if (this.syncFrame || !this.audio) {
      return;
    }
    const duration = this.trackDuration ?? this.audio.duration;
    if (!Number.isFinite(duration) || duration <= 0) {
      if (!this.pendingStartSync) {
        this.pendingStartSync = true;
        const startWhenReady = () => {
          this.pendingStartSync = false;
          if (this.audio && !this.audio.paused && !this.audio.ended) {
            this.startSync();
          }
        };
        this.audio.addEventListener("loadedmetadata", startWhenReady, { once: true });
        this.audio.addEventListener("durationchange", startWhenReady, { once: true });
      }
      return;
    }
    const tick = () => {
      if (!this.audio || this.audio.paused || this.audio.ended) {
        this.syncFrame = null;
        return;
      }
      this.renderAt(this.audio.currentTime);
      this.syncFrame = window.requestAnimationFrame(tick);
    };
    this.syncFrame = window.requestAnimationFrame(tick);
  }

  stopSync() {
    if (this.syncFrame) {
      window.cancelAnimationFrame(this.syncFrame);
      this.syncFrame = null;
    }
    this.pendingStartSync = false;
  }

  drawPlaceholder(title, artist, detail) {
    if (!this.context || !this.canvas) {
      return;
    }
    const { width, height } = this.canvas;
    this.context.clearRect(0, 0, width, height);
    this.context.fillStyle = "#000";
    this.context.fillRect(0, 0, width, height);
    this.context.fillStyle = "#f5f5f5";
    this.context.textAlign = "center";
    this.context.font = "bold 42px Arial, sans-serif";
    this.context.fillText(title, width / 2, height / 2 - 20);
    this.context.font = "26px Arial, sans-serif";
    this.context.fillText(artist, width / 2, height / 2 + 20);
    this.context.font = "20px Arial, sans-serif";
    this.context.fillStyle = "#7ec8ff";
    this.context.fillText(detail, width / 2, height / 2 + 60);
  }

  stop() {
    this.stopSync();
    this.current = null;
    this.loaded = false;
    this.trackDuration = null;
    this.packets = [];
    this.nextPacketIndex = 0;
    this.resetState();
    this.drawPlaceholder("Select a song", "", "Ready for browser playback");
  }
}

window.CDGPlayer = CDGPlayer;
