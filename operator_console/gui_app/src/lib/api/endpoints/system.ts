import { apiGet } from "@/lib/api/client";
import type { HomePageData, LatestMetrics, SystemStatus } from "@/types";

export const getStatus = () => apiGet<SystemStatus>("/status");

export const getHome = () => apiGet<HomePageData>("/home");

export const getDashboardSummary = () => apiGet<Record<string, number>>("/dashboard-summary");

export const getLatestMetrics = () => apiGet<LatestMetrics>("/latest-metrics");
