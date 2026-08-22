# 🚀 Quick Start Guide — Bengaluru Pulse

Get the entire system running in **under 3 minutes**.

---

## ✅ Prerequisites

- **Python 3.8+** installed
- **Node.js 16+** and npm installed
- **Terminal** (cmd, PowerShell, or bash)

---

## 🔥 Step-by-Step Launch

### **Step 1: Start the Backend API**

```bash
# Navigate to backend folder
cd backend

# Install Python dependencies (first time only)
pip install -r requirements.txt

# Start the FastAPI server
uvicorn main:app --reload
```

✅ **Backend is live at**: `http://127.0.0.1:8000`  
📖 **API Docs**: `http://127.0.0.1:8000/docs`

**Keep this terminal open!**

---

### **Step 2: Start the Frontend**

Open a **NEW terminal** window:

```bash
# Navigate to frontend folder
cd frontend

# Install dependencies (first time only)
npm install --legacy-peer-deps

# Start React development server
npm start
```

✅ **Frontend is live at**: `http://localhost:3000`

Your browser should automatically open. If not, manually navigate to the URL.

---

## 🎯 Using the Application

### **Dashboard Tab** (Default View)
1. Select a **Location** (e.g., Silk Board)
2. Enter **Traffic Volume** (e.g., 250) — Range: 0–500
3. Enter **Average Speed** (e.g., 15) — Range: 0–120 km/h
4. Click **"⚡ Predict Traffic"**
5. View:
   - Congestion Index (0–30 scale)
   - Status (LOW/MODERATE/HIGH/SEVERE)
   - Estimated Delay
   - AI Recommendations

### **Live Map Tab**
- Interactive map with pulse markers
- Click any location to select it
- View real-time congestion colors

### **12h Forecast Tab**
- Select a location
- See predicted congestion for next 12 hours
- Peak and best travel windows highlighted

### **Hotspot Heatmap Tab**
- Compare all 6 locations
- Ranked by current congestion
- City average baseline shown

### **Historical Trends Tab**
- 7-day comparison chart
- Multi-location trends
- Best/worst location identification

### **Commute Advisor Tab**
- Select origin and destination
- Set preferred arrival time
- Get departure time suggestions
- View alternate route options

---

## 🛠️ Troubleshooting

### **Backend Error: "Module not found"**
```bash
pip install fastapi uvicorn pandas scikit-learn joblib
```

### **Frontend Error: "Cannot find module"**
```bash
cd frontend
npm install --legacy-peer-deps
```

### **Port 8000 already in use**
```bash
# Change port in backend
uvicorn main:app --reload --port 8001

# Update frontend/.env
REACT_APP_API_BASE_URL=http://127.0.0.1:8001
```

### **Port 3000 already in use**
```bash
# Windows: Set port before npm start
set PORT=3001 && npm start

# Or React will prompt you to use a different port
```

### **Map not loading**
- Ensure internet connection (Leaflet tiles require online access)
- Check browser console for errors
- Verify Leaflet script loaded in `public/index.html`

### **Predictions returning errors**
- Verify backend is running at `http://127.0.0.1:8000`
- Check backend terminal for error logs
- Ensure `.pkl` model files exist in backend folder

---

## 📦 File Structure

```
BengaluruPulseLite/
├── backend/
│   ├── main.py                  # FastAPI app with 7 endpoints
│   ├── train_model.py           # ML model training script
│   ├── traffic_model.pkl        # Trained RandomForest model
│   ├── area_encoder.pkl         # Area label encoder
│   ├── road_encoder.pkl         # Road label encoder
│   ├── weather_encoder.pkl      # Weather label encoder
│   └── Banglore_traffic_Dataset.csv
│
├── frontend/
│   ├── src/
│   │   ├── App.js               # Main React component
│   │   ├── App.css              # Design system
│   │   └── components/
│   │       ├── AlertBanner.js
│   │       ├── CongestionGauge.js
│   │       ├── CommuteAdvisor.js
│   │       ├── ForecastPanel.js
│   │       ├── HistoricalTrends.js
│   │       ├── HotspotHeatmap.js
│   │       └── TrafficMap.js
│   ├── public/
│   │   └── index.html           # Leaflet script injection
│   └── package.json
│
├── README.md
└── QUICKSTART.md
```

---

## 🎓 Testing Scenarios

### **Scenario 1: Morning Rush Hour**
- Location: **Silk Board**
- Traffic Volume: **300**
- Average Speed: **12**
- Weather: **Sunny**
- Expected: **SEVERE** congestion

### **Scenario 2: Smooth Flow**
- Location: **Electronic City**
- Traffic Volume: **50**
- Average Speed: **70**
- Weather: **Sunny**
- Expected: **LOW** congestion

### **Scenario 3: Rainy Day Impact**
- Location: **Marathahalli Bridge**
- Traffic Volume: **200**
- Average Speed: **25**
- Weather: **Rainy**
- Expected: **HIGH** congestion (weather adds +5 penalty)

---

## 💡 Pro Tips

1. **Switch Weather** — Top-right weather selector affects all predictions
2. **Mem-Brain Memory** — Make 3+ predictions to see behavioral insights
3. **Peak Hours** — Check map for ⚡ Peak badges (8-10 AM, 5-8 PM)
4. **City Average** — Hotspot Heatmap shows baseline congestion
5. **Best Travel Window** — Forecast tab highlights optimal departure times

---

## 🔗 Quick Links

- **Backend API Docs**: http://127.0.0.1:8000/docs
- **Frontend UI**: http://localhost:3000
- **GitHub Repo**: *(add your repo URL)*

---

## 📞 Need Help?

- Check backend terminal for API errors
- Check browser console (F12) for frontend errors
- Ensure both servers are running simultaneously
- Verify all `.pkl` files exist in backend folder

---

**Happy Traffic Monitoring! 🚦**
