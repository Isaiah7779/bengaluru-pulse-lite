# Project status

## Working and verified

- FastAPI health, locations, and model-prediction endpoints.
- OSRM client and diverse candidate routing logic.
- Strict shortcut and longcut classification based on both distance and time.
- React dashboard unit test and production build.
- Container definitions for frontend, backend, and the mounted Bengaluru OSRM graph.

## External configuration required

- OSRM runtime: Docker Desktop or a separately hosted OSRM service.
- Live traffic: a valid TomTom API key.
- Weather, incidents, historical traffic collection, PostGIS, authentication,
  and community routes are not marked complete because no real provider/data
  pipeline is configured for them. The application does not fabricate these data.
