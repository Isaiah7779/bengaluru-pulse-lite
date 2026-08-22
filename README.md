# 🚦 Bengaluru Pulse — AI-Powered Urban Traffic Intelligence System

**A production-ready, ML-powered traffic forecasting and smart-city transportation platform designed to address Bengaluru's notorious congestion challenges.**

---

## 🎯 Vision

Design and develop an **AI-powered Urban Traffic Intelligence System** that leverages:
- **Machine Learning** for congestion prediction
- **Real-time environmental data** integration
- **Predictive analytics** with 12-hour forecasting
- **Intelligent visualization** with interactive maps and charts
- **Scalable foundation** for future smart-city transportation systems

---

## 🏗️ Architecture

### **Backend** (FastAPI + Python)
- **7 REST API Endpoints** providing comprehensive traffic intelligence
- **RandomForest ML Model** trained on Bangalore traffic dataset
- **Real-time computation** using Gaussian peak modeling (8:30 AM & 6:30 PM rush hours)
- **Multi-location support** — 6 key traffic hotspots across Bengaluru
- **Weather-aware predictions** — Sunny/Cloudy/Rainy conditions

### **Frontend** (React 19 + Modern Stack)
- **6 Interactive Dashboards** — Dashboard, Live Map, 12h Forecast, Hotspots, Trends, Commute Advisor
- **Real-time visualization** — Leaflet maps, Recharts analytics, Framer Motion animations
- **Glassmorphism UI** — Modern design system with backdrop blur effects
- **Responsive design** — Mobile-first approach
- **Mem-Brain Engine** — localStorage-based traffic memory and behavioral insights

---

## 🚀 Features

### **1. Traffic Prediction Dashboard**
- Real-time congestion prediction (0–30 index scale)
- Input: Location, Traffic Volume, Average Speed, Weather
- Output: Congestion level (LOW/MODERATE/HIGH/SEVERE), signal status, delay estimate
- **Mem-Brain Engine** learns from historical predictions

### **2. Live Interactive Map**
- Leaflet map with animated pulse markers
- Color-coded congestion indicators per location
- Click-to-select locations with auto-pan
- Real-time hotspot overlays

### **3. 12-Hour Forecast**
- Predictive congestion curve using time-series modeling
- Peak congestion detection
- Best travel window recommendations
- Area chart visualization with severity bands

### **4. Hotspot Heatmap**
- Horizontal bar chart ranking all 6 locations
- City-wide average baseline
- Peak hour indicators
- Top 3 congestion rankings with medals

### **5. Historical Trends**
- 7-day multi-location comparison
- City-wide average trend line
- Identify best/worst locations by day

### **6. Commute Advisor**
- AI-powered departure time suggestions
- Origin → Destination route planning
- Alternate route recommendations (ORR, NICE Road, Metro)
- Estimated travel time & delay forecasting

### **7. Alert System**
- Live banner for SEVERE/HIGH congestion alerts
- Cycling through multiple alerts
- Color-coded urgency indicators

---

## 📊 Supported Locations

1. **Marathahalli Bridge** — Major IT corridor bridge (Outer Ring Road)
2. **Silk Board** — Notorious bottleneck junction (3-road merge)
3. **KR Puram** — Eastern gateway with heavy freight traffic
4. **Hebbal** — Northern flyover linking airport corridor
5. **Whitefield** — Prime IT hub with tech-park density
6. **Electronic City** — Southern tech corridor with elevated highway

---

## 🛠️ Tech Stack

### **Backend**
- **FastAPI** — High-performance async Python web framework
- **Scikit-learn** — RandomForest ML model
- **Pandas** — Data processing
- **Joblib** — Model serialization
- **LabelEncoder** — Categorical feature encoding

### **Frontend**
- **React 19.2.6** — Component-based UI
- **Recharts 5.3.1** — Declarative charting library
- **Leaflet + React-Leaflet** — Interactive maps
- **Framer Motion** — Smooth animations
- **Axios** — HTTP client
- **React Icons** — Icon set
- **date-fns** — Date utilities

### **Design System**
- **Glassmorphism** — Backdrop blur effects
- **CSS Custom Properties** — Theming
- **Responsive Grid** — Mobile-first layout
- **Dark Theme** — Eye-friendly UI

---

## 📦 Installation & Setup

### **1. Backend Setup**

```bash
cd backend

# Install Python dependencies
pip install -r requirements.txt

# Train the ML model (if not already trained)
python train_model.py

# Start the FastAPI server
uvicorn main:app --reload
```

Backend will run at: `http://127.0.0.1:8000`

API Documentation (Swagger): `http://127.0.0.1:8000/docs`

---

### **2. Frontend Setup**

```bash
cd frontend

# Install dependencies
npm install --legacy-peer-deps

# Optional: override backend URL
# Create .env from .env.example and set REACT_APP_API_BASE_URL if needed.

# Start development server
npm start
```

Frontend will run at: `http://localhost:3000`

---

## 🔌 API Endpoints

### **Base URL**: `http://127.0.0.1:8000`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API health check |
| `/locations` | GET | List all locations with coordinates |
| `/predict` | POST | Predict congestion for given inputs |
| `/forecast` | POST | 12-hour ahead forecast for location |
| `/hotspots` | GET | Current congestion across all locations |
| `/analytics` | GET | 24-hour congestion profile & risk score |
| `/commute-advisor` | POST | Departure time & route recommendations |
| `/historical-trends` | GET | 7-day historical data |

---

## 📝 Example API Usage

### **Predict Congestion**
```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Silk Board",
    "traffic_volume": 250,
    "average_speed": 15,
    "weather": "Rainy"
  }'
```

**Response:**
```json
{
  "predicted_congestion": 23.4,
  "traffic_status": "SEVERE",
  "signal": "RED",
  "recommendation": "Severe gridlock at Silk Board. Immediate alternate route advised...",
  "density_percent": 93.6,
  "estimated_delay_minutes": 35.5
}
```

---

## 🎨 UI Screenshots

*(Since this is text, imagine these sections with beautiful screenshots)*

### Dashboard View
- Prediction form + Congestion Gauge + Explainable AI card + Analytics

### Live Map
- Interactive Leaflet map with pulse markers

### 12-Hour Forecast
- Area chart with peak/trough highlights

### Hotspot Heatmap
- Horizontal bar chart with rankings

### Historical Trends
- Multi-line chart comparing all locations

### Commute Advisor
- Departure suggestions + Route alternatives

---

## 🧠 Mem-Brain Engine

The **Mem-Brain Engine** is a local AI memory system that:
- Stores all predictions in `localStorage`
- Analyzes the last 3 predictions for behavioral patterns
- Provides location-specific insights
- Recommends alternate routes based on recurring congestion

**Example Insight:**
> "Silk Board shows repeated severe congestion patterns. Mem-Brain recommends alternate route planning."

---

## 🔮 Future Enhancements

1. **Real-time CCTV integration** — Live camera feeds
2. **Mobile app** — React Native version
3. **Public transit API** — BMTC bus and Namma Metro ETA
4. **User authentication** — Save favorite routes
5. **Push notifications** — Congestion alerts
6. **Voice assistant** — "Alexa, what's the traffic at Silk Board?"
7. **ML model improvements** — LSTM/Transformer for time-series
8. **Crowd-sourced data** — User-reported incidents
9. **Carbon footprint tracker** — Eco-friendly route suggestions
10. **Integration with Google Maps** — Navigation handoff

---

## 👥 Contributors

- **Your Name** — Full-Stack Developer & ML Engineer

---

## 📄 License

MIT License — Free to use and modify

---

## 🙏 Acknowledgments

- **Bangalore Traffic Dataset** — Training data source
- **Open-Meteo API** — Weather data provider
- **Leaflet.js** — Open-source mapping library
- **FastAPI** — Modern Python web framework

---

## 📞 Contact

For questions, collaborations, or feedback:
- **Email**: your.email@example.com
- **GitHub**: github.com/yourusername
- **LinkedIn**: linkedin.com/in/yourusername

---

**Built with ❤️ for Bengaluru's commuters**
