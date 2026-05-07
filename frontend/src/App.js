import React, { useState } from "react";
import axios from "axios";

function App() {

  const [trafficVolume, setTrafficVolume] = useState("");
  const [averageSpeed, setAverageSpeed] = useState("");
  const [weather, setWeather] = useState("Clear");
  const [prediction, setPrediction] = useState("");

  const predictTraffic = async () => {

    try {

      const response = await axios.post(
        "http://127.0.0.1:8000/predict",
        {
          traffic_volume: parseInt(trafficVolume),
          average_speed: parseFloat(averageSpeed),
          weather: weather
        }
      );

      setPrediction(response.data.predicted_congestion);

    } catch (error) {
      console.log(error);
      alert("Prediction Failed");
    }
  };

  return (
    <div
      style={{
        fontFamily: "Arial",
        padding: "40px",
        backgroundColor: "#f4f4f4",
        minHeight: "100vh"
      }}
    >

      <h1>Bengaluru Pulse Lite</h1>

      <h2>
        Marathahalli Bridge Traffic Prediction
      </h2>

      <br />

      <input
        type="number"
        placeholder="Traffic Volume"
        value={trafficVolume}
        onChange={(e) =>
          setTrafficVolume(e.target.value)
        }
        style={{
          padding: "10px",
          width: "300px"
        }}
      />

      <br /><br />

      <input
        type="number"
        placeholder="Average Speed"
        value={averageSpeed}
        onChange={(e) =>
          setAverageSpeed(e.target.value)
        }
        style={{
          padding: "10px",
          width: "300px"
        }}
      />

      <br /><br />

      <select
        value={weather}
        onChange={(e) =>
          setWeather(e.target.value)
        }
        style={{
          padding: "10px",
          width: "320px"
        }}
      >
        <option>Clear</option>
        <option>Fog</option>
        <option>Overcast</option>
        <option>Rain</option>
        <option>Windy</option>
      </select>

      <br /><br />

      <button
        onClick={predictTraffic}
        style={{
          padding: "12px 20px",
          backgroundColor: "#007bff",
          color: "white",
          border: "none",
          cursor: "pointer"
        }}
      >
        Predict Traffic
      </button>

      <br /><br />

      <h2>
        Predicted Congestion:
        {" "}
        {prediction}
      </h2>

    </div>
  );
}

export default App;