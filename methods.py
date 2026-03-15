import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import RANSACRegressor
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt
from llm import build_llm_market_input

# ----------------------------
# Pivot detection
# ----------------------------
def detect_pivots(prices, distance=4, prominence=0.002):

    peaks, _ = find_peaks(prices, distance=distance, prominence=prominence)
    lows, _ = find_peaks(-prices, distance=distance, prominence=prominence)

    return peaks, lows


# ----------------------------
# Trendline
# ----------------------------
def detect_trendline(prices):

    x = np.arange(len(prices))

    model = RANSACRegressor()
    model.fit(x.reshape(-1,1), prices)

    return model.predict(x.reshape(-1,1))


# ----------------------------
# Zone detection -> lines
# ----------------------------
def detect_zone_lines(levels, eps):

    if len(levels) < 2:
        return []

    X = np.array(levels).reshape(-1,1)

    clustering = DBSCAN(eps=eps, min_samples=2).fit(X)

    labels = clustering.labels_

    zones = []

    for label in set(labels):

        if label == -1:
            continue

        cluster = X[labels == label].flatten()

        # convert cluster into sorted lines
        lines = sorted(cluster.tolist())

        zones.append(lines)

    return zones


# ----------------------------
# Main detection
# ----------------------------
def detect_levels(close_prices):

    prices = np.array(close_prices)

    peaks, lows = detect_pivots(prices)

    resistance_levels = prices[peaks]
    support_levels = prices[lows]

    price_range = np.max(prices) - np.min(prices)

    resistance_zones = detect_zone_lines(
        resistance_levels,
        eps=price_range*0.02
    )

    support_zones = detect_zone_lines(
        support_levels,
        eps=price_range*0.02
    )

    trend = detect_trendline(prices)

    return trend, resistance_zones, support_zones, peaks, lows


# ----------------------------
# Plot chart
# ----------------------------
def plot_chart(close_prices, save_path="chart.png"):

    trend, resistance_zones, support_zones, peaks, lows = detect_levels(close_prices)

    prices = np.array(close_prices)
    x = np.arange(len(prices))

    plt.figure(figsize=(12,6))

    plt.plot(prices, label="Close Price")
    plt.plot(x, trend, label="Trendline")

    # resistance lines
    for zone in resistance_zones:
        for level in zone:
            plt.axhline(level)

    # support lines
    for zone in support_zones:
        for level in zone:
            plt.axhline(level)

    plt.scatter(peaks, prices[peaks])
    plt.scatter(lows, prices[lows])

    plt.legend()

    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()

    return save_path