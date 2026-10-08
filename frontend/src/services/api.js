import axios from "axios";

export const LOCAL_API_URL =
  import.meta.env.VITE_LOCAL_API_URL ||
  "http://127.0.0.1:8000/api/";

export const RENDER_API_URL =
  import.meta.env.VITE_RENDER_API_URL ||
  "https://hospital-management-backend-ld3y.onrender.com/api/";

export const getActiveApiUrl = () => {
  const envUrl = import.meta.env.VITE_API_URL;

  if (envUrl && envUrl !== "undefined" && envUrl !== "/") {
    return envUrl;
  }

  return RENDER_API_URL;
};

const API = axios.create({
  baseURL: getActiveApiUrl(),
});

API.interceptors.request.use(
  (config) => {
    if (!config.baseURL) {
      config.baseURL = getActiveApiUrl();
    }

    const token = localStorage.getItem("token");

    if (token) {
      config.headers.Authorization = `Token ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

API.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      !error.response &&
      originalRequest &&
      !originalRequest._retryWithLocal &&
      originalRequest.baseURL === RENDER_API_URL
    ) {
      originalRequest._retryWithLocal = true;
      originalRequest.baseURL = LOCAL_API_URL;

      return API(originalRequest);
    }

    if (error.response?.status === 401) {
      localStorage.removeItem("isLoggedIn");
      localStorage.removeItem("token");
      localStorage.removeItem("role");
      localStorage.removeItem("currentUser");

      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }

    return Promise.reject(error);
  }
);

export default API;