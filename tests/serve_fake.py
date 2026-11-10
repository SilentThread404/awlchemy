import sys; sys.path[:0] = [".", "tests"]
import fake_claude; fake_claude.install()
import uvicorn
uvicorn.run("awlchemy.app:app", host="127.0.0.1", port=8765, log_level="warning")
