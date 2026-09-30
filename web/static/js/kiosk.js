const nameInput = document.getElementById("name");

function kioskCanAutoRefresh() {
  if (!nameInput) return true;
  if (document.activeElement === nameInput) return false;
  return nameInput.value.trim() === "";
}

setInterval(() => {
  if (kioskCanAutoRefresh()) {
    window.location.reload();
  }
}, 12000);
