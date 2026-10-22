import { render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import App from "./App";

jest.mock("axios");
jest.mock("./components/TrafficMap", () => () => (
  <div data-testid="traffic-map" />
));

beforeEach(() => {
  axios.get.mockImplementation((url) => {
    if (url.includes("/hotspots")) {
      return Promise.resolve({
        data: {
          hotspots: [],
          worst_location: null,
          best_location: null,
          city_average_congestion: 0,
        },
      });
    }
    if (url.includes("/historical-trends")) {
      return Promise.resolve({ data: { trend_data: [], locations: [], city_trend: [] } });
    }
    if (url.includes("/incidents")) {
      return Promise.resolve({ data: { status: "ok", incidents: [] } });
    }
    if (url.includes("/analytics")) {
      return Promise.resolve({ data: null });
    }
    return Promise.resolve({ data: {} });
  });

  axios.post.mockResolvedValue({
    data: {
      location: "Silk Board",
      forecast: [],
    },
  });
});

test("renders Bengaluru Pulse dashboard", async () => {
  render(<App />);
  expect(screen.getByText("Bengaluru Pulse")).toBeInTheDocument();
  expect(screen.getByText("Traffic Prediction")).toBeInTheDocument();
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
  await waitFor(() => expect(axios.post).toHaveBeenCalled());
});
