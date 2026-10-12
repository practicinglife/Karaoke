"""Desktop entrypoint for Karaoke Ticker GUI."""

import sys

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        # Install check for the stage screen; never opens the GUI or the database.
        from stage.selftest import run

        args = sys.argv[sys.argv.index("--self-test") + 1 :]
        sys.exit(run(args[0] if args else None))

    from gui import KaraokeTickerGUI

    app = KaraokeTickerGUI()
    app.mainloop()
