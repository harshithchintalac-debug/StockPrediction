from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import numpy as np
import os
import joblib
from tensorflow.keras.models import load_model
import pandas as pd
from datetime import datetime, timedelta
from src.utils import load_close_series


app = FastAPI(title="StockTrendAI")


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "models", "lstm_close_model.h5")
SCALER_PATH = os.path.join(BASE_DIR, "models", "lstm_scaler.pkl")
DATA_PATH = os.path.join(BASE_DIR, "data", "dataset.csv")


templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "app", "templates"))
app.mount("/static", StaticFiles(directory="app/static"), name="static")


try:
    model = load_model(MODEL_PATH, compile=False)
    scaler = joblib.load(SCALER_PATH)
    print(" Model and Scaler loaded successfully.")
except Exception as e:
    print(" Error loading model or scaler:", e)
    model, scaler = None, None

# LSTM sequence length (must match training)
n_steps = 10


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page route — renders index.html"""
    return templates.TemplateResponse(
        "index.html", {"request": request, "preds": None, "history": None}
    )


@app.post("/predict", response_class=HTMLResponse)
async def predict(request: Request, days: int = Form(...)):
    """Predict route — generates future closing prices"""
    try:
        if model is None or scaler is None:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "Model or scaler not loaded. Please train the model first.",
                },
            )

        # Load dataset
        df = load_close_series(DATA_PATH)
        print("✅ CSV Loaded Successfully. Columns:", df.columns.tolist())

        # Normalize column names (case-insensitive)
        df.columns = df.columns.str.strip().str.lower()

        # Check if essential columns exist
        if "close" not in df.columns:
            raise KeyError("Column 'close' not found in dataset.")
        if "date" not in df.columns:
            raise KeyError("Column 'date' not found in dataset.")

        # Convert 'date' column to datetime if not already
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # Remove rows with invalid dates
        df = df.dropna(subset=["date"])

        last_vals = df["close"].values[-n_steps:]

        # Forecast loop
        preds = []
        seq = last_vals.copy()
        for _ in range(days):
            scaled_seq = scaler.transform(np.array(seq[-n_steps:]).reshape(-1, 1))
            yhat = model.predict(scaled_seq.reshape(1, n_steps, 1), verbose=0)
            inv = scaler.inverse_transform(yhat)[0][0]
            preds.append(inv)
            seq = np.append(seq, inv)

        # Build future dates
        last_date = df["date"].iloc[-1]
        future_dates = [
            (last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d")
            for i in range(days)
        ]

        # Convert timestamps to strings
        df["date"] = df["date"].astype(str)

        print(" Prediction completed successfully!")

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "preds": list(zip(future_dates, [round(float(p), 2) for p in preds])),
                "history": df.tail(60).to_dict(orient="records"),
            },
        )

    except Exception as e:
        import traceback
        print("\n ERROR in /predict:", e)
        traceback.print_exc()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"Prediction failed: {e}"},
        )
