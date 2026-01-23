from dotenv import load_dotenv
import uvicorn

load_dotenv("keyazure.env")
load_dotenv("keyadmin.env")

if __name__ == "__main__":
    uvicorn.run("API.main:app", host="127.0.0.1", port=8000, reload=True)
