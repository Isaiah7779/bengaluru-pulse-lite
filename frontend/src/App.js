import React, {
  useState,
  useEffect
} from "react";

import axios from "axios";

import {
  Line
} from "react-chartjs-2";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from "chart.js";

import {
  FaTrafficLight,
  FaCloudRain,
  FaMapMarkedAlt,
  FaRoad,
  FaMapMarkerAlt,
  FaRobot,
  FaClock
} from "react-icons/fa";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

function App() {

  const locationMaps = {

    "Marathahalli Bridge":
      "https://www.google.com/maps?q=Marathahalli+Bridge+Bangalore&output=embed&layer=t",

    "Silk Board":
      "https://www.google.com/maps?q=Silk+Board+Bangalore&output=embed&layer=t",

    "KR Puram":
      "https://www.google.com/maps?q=KR+Puram+Bangalore&output=embed&layer=t",

    "Hebbal":
      "https://www.google.com/maps?q=Hebbal+Flyover+Bangalore&output=embed&layer=t",

    "Whitefield":
      "https://www.google.com/maps?q=Whitefield+Bangalore&output=embed&layer=t",

    "Electronic City":
      "https://www.google.com/maps?q=Electronic+City+Bangalore&output=embed&layer=t"
  };

  const locationCoordinates = {

    "Marathahalli Bridge": {
      lat: 12.9591,
      lon: 77.6974
    },

    "Silk Board": {
      lat: 12.9177,
      lon: 77.6238
    },

    "KR Puram": {
      lat: 13.0077,
      lon: 77.6955
    },

    "Hebbal": {
      lat: 13.0358,
      lon: 77.5970
    },

    "Whitefield": {
      lat: 12.9698,
      lon: 77.7500
    },

    "Electronic City": {
      lat: 12.8456,
      lon: 77.6603
    }
  };

  const [trafficVolume, setTrafficVolume] =
    useState("");

  const [averageSpeed, setAverageSpeed] =
    useState("");

  const [weather, setWeather] =
    useState("Loading...");

  const [prediction, setPrediction] =
    useState("");

  const [location, setLocation] =
    useState("Marathahalli Bridge");

  const [currentTime, setCurrentTime] =
    useState("");

  const [history, setHistory] =
    useState([]);

  useEffect(() => {

    fetchWeather();

  }, [location]);

  useEffect(() => {

    const timer = setInterval(() => {

      const now = new Date();

      setCurrentTime(
        now.toLocaleString()
      );

    }, 1000);

    return () => clearInterval(timer);

  }, []);

  const fetchWeather = async () => {

    try {

      const coords =
        locationCoordinates[location];

      const response = await axios.get(

        `https://api.open-meteo.com/v1/forecast?latitude=${coords.lat}&longitude=${coords.lon}&current_weather=true`
      );

      const temperature =
        response.data.current_weather.temperature;

      if (temperature < 18) {
        setWeather("Fog");
      }

      else if (temperature < 24) {
        setWeather("Overcast");
      }

      else if (temperature < 30) {
        setWeather("Clear");
      }

      else {
        setWeather("Rain");
      }

    } catch (error) {

      console.log(error);

      setWeather("Clear");
    }
  };

  const predictTraffic = async () => {

    if (
      trafficVolume < 0 ||
      trafficVolume > 500
    ) {
      alert("Traffic Volume must be between 0 and 500");
      return;
    }

    if (
      averageSpeed < 0 ||
      averageSpeed > 120
    ) {
      alert("Average Speed must be between 0 and 120 km/h");
      return;
    }

    try {

      const response = await axios.post(
        "http://127.0.0.1:8000/predict",
        {
          traffic_volume:
            parseInt(trafficVolume),

          average_speed:
            parseFloat(averageSpeed),

          location: location,

          weather: weather
        }
      );

      let predictedValue =
        response.data.predicted_congestion;

      if (
        trafficVolume < 20 &&
        averageSpeed > 60
      ) {
        predictedValue = 5;
      }

      else if (
        trafficVolume > 250 &&
        averageSpeed < 20
      ) {
        predictedValue += 5;
      }

      predictedValue =
        Number(predictedValue.toFixed(2));

      setPrediction(predictedValue);

      setHistory(prev => [
        ...prev,
        predictedValue
      ]);

    } catch (error) {

      console.log(error);

      alert("Prediction Failed");
    }
  };

  const getTrafficStatus = () => {

    if (prediction < 8) {
      return "LOW";
    }

    else if (prediction < 15) {
      return "MODERATE";
    }

    else if (prediction < 22) {
      return "HIGH";
    }

    else {
      return "SEVERE";
    }
  };

  const getStatusColor = () => {

    if (prediction < 8) {
      return "#00ff99";
    }

    else if (prediction < 15) {
      return "#ffcc00";
    }

    else if (prediction < 22) {
      return "#ff8800";
    }

    else {
      return "#ff3333";
    }
  };

  const getSignal = () => {

    if (prediction < 8) {
      return "🟢 GREEN";
    }

    else if (prediction < 15) {
      return "🟡 YELLOW";
    }

    else {
      return "🔴 RED";
    }
  };

  const getRecommendation = () => {

    if (prediction < 8) {
      return "Traffic flow is smooth. Normal route recommended.";
    }

    else if (prediction < 15) {
      return "Moderate congestion detected. Consider alternate roads.";
    }

    else if (prediction < 22) {
      return "Heavy congestion detected. Delay expected.";
    }

    else {
      return "Severe congestion detected. Use alternate route immediately.";
    }
  };

  const chartData = {

    labels: history.map((_, index) =>
      `P${index + 1}`
    ),

    datasets: [
      {
        label: "Congestion Trend",
        data: history,
        borderColor: "#00bfff",
        backgroundColor: "rgba(0,191,255,0.2)",
        tension: 0.4
      }
    ]
  };

  return (

    <div
      style={{
        minHeight: "100vh",

        background:
          "linear-gradient(to right, #0f2027, #203a43, #2c5364)",

        color: "white",

        fontFamily: "Arial",

        padding: "25px"
      }}
    >

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center"
        }}
      >

        <div>

          <h1
            style={{
              fontSize: "42px"
            }}
          >
            🚦 Bengaluru Pulse Lite
          </h1>

          <p
            style={{
              color: "#cccccc"
            }}
          >
            AI-Powered Smart City Traffic Intelligence Dashboard
          </p>

        </div>

        <div style={glassCard}>

          <h3>
            <FaClock /> Bengaluru Time
          </h3>

          <h2>
            {currentTime}
          </h2>

        </div>

      </div>

      <br />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "20px"
        }}
      >

        <div style={cardStyle}>
          <h3>Traffic Status</h3>
          <h1 style={{ color: getStatusColor() }}>
            {prediction ? getTrafficStatus() : "--"}
          </h1>
        </div>

        <div style={cardStyle}>
          <h3>Signal Status</h3>
          <h1>
            {prediction ? getSignal() : "--"}
          </h1>
        </div>

        <div style={cardStyle}>
          <h3>Weather</h3>
          <h1>
            {weather}
          </h1>
        </div>

        <div style={cardStyle}>
          <h3>Density</h3>
          <h1>
            {prediction ? `${Math.min(prediction * 4, 100).toFixed(0)}%` : "--"}
          </h1>
        </div>

      </div>

      <br />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "25px"
        }}
      >

        <div style={glassCard}>

          <h2>
            <FaTrafficLight /> Traffic Prediction
          </h2>

          <br />

          <select
            value={location}
            onChange={(e) =>
              setLocation(e.target.value)
            }
            style={inputStyle}
          >

            <option>Marathahalli Bridge</option>
            <option>Silk Board</option>
            <option>KR Puram</option>
            <option>Hebbal</option>
            <option>Whitefield</option>
            <option>Electronic City</option>

          </select>

          <br /><br />

          <input
            type="number"
            placeholder="Traffic Volume"
            value={trafficVolume}
            onChange={(e) =>
              setTrafficVolume(e.target.value)
            }
            style={inputStyle}
          />

          <br /><br />

          <input
            type="number"
            placeholder="Average Speed"
            value={averageSpeed}
            onChange={(e) =>
              setAverageSpeed(e.target.value)
            }
            style={inputStyle}
          />

          <br /><br />

          <button
            onClick={predictTraffic}
            style={buttonStyle}
          >
            Predict Traffic
          </button>

          <br /><br />

          <div
            style={{
              background: "rgba(0,0,0,0.3)",
              padding: "20px",
              borderRadius: "15px",
              textAlign: "center"
            }}
          >

            <h2>
              Predicted Congestion
            </h2>

            <h1
              style={{
                color: getStatusColor(),
                fontSize: "60px"
              }}
            >
              {prediction || "--"}
            </h1>

          </div>

        </div>

        <div style={glassCard}>

          <h2>
            <FaMapMarkedAlt />
            {" "}
            {location} Live Traffic
          </h2>

          <br />

          <iframe
            title="map"
            src={locationMaps[location]}
            width="100%"
            height="320"
            style={{
              border: "0",
              borderRadius: "15px"
            }}
            allowFullScreen=""
            loading="lazy"
          ></iframe>

        </div>

      </div>

      <br />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "25px"
        }}
      >

        <div style={glassCard}>

          <h2>
            📈 Congestion Analytics
          </h2>

          <Line data={chartData} />

        </div>

        <div style={glassCard}>

          <h2>
            <FaRobot /> AI Recommendation
          </h2>

          <br />

          <p
            style={{
              fontSize: "18px",
              lineHeight: "1.8",
              color: "#dddddd"
            }}
          >
            {prediction
              ? getRecommendation()
              : "Run a prediction to receive AI recommendations."}
          </p>

          <br />

          <h3>
            Explainable AI
          </h3>

          <ul>
            <li>
              Weather Condition: {weather}
            </li>
            <li>
              Traffic Volume: {trafficVolume || "--"}
            </li>
            <li>
              Average Speed: {averageSpeed || "--"}
            </li>
            <li>
              Location: {location}
            </li>
          </ul>

        </div>

      </div>

      <br />

      <div
        style={{
          textAlign: "center",
          color: "#cccccc"
        }}
      >
        <FaRoad /> Bengaluru Pulse Lite • Ultimate Smart City Dashboard
      </div>

    </div>
  );
}

const glassCard = {

  background: "rgba(255,255,255,0.08)",
  padding: "25px",
  borderRadius: "20px",
  backdropFilter: "blur(10px)"
};

const cardStyle = {

  background: "rgba(255,255,255,0.08)",
  padding: "20px",
  borderRadius: "20px",
  textAlign: "center",
  backdropFilter: "blur(10px)"
};

const inputStyle = {

  width: "100%",
  padding: "14px",
  borderRadius: "10px",
  border: "none",
  fontSize: "16px",
  outline: "none"
};

const buttonStyle = {

  background: "#00bfff",
  border: "none",
  padding: "14px 20px",
  color: "white",
  fontSize: "16px",
  borderRadius: "10px",
  cursor: "pointer",
  width: "100%"
};

export default App;