import os

import uvicorn

# The gateway lives on 11500/12500; keep the console below it on 12000 so the
# three endpoints sit in one band and nothing collides with the usual 8000/8080
# crowd. Override with NP_HOST / NP_PORT.
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("NP_HOST", "127.0.0.1"),
        port=int(os.getenv("NP_PORT", "12000")),
        log_level=os.getenv("NP_LOG", "info"),
    )
