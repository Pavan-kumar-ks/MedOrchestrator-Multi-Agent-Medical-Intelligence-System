from typing import Dict, Any, List
import math

from app.tools.mcp_maps import geocode_location, find_nearby_hospitals, get_place_details, get_travel_time


def hospital_finder_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Find nearby hospitals within 5km of the user's location.

    Expects: state["location"] = {"text": "..."} or {"lat": .., "lng": ..}
    Returns: {"hospitals": [ ... ]}
    """
    loc = state.get("location") or {}
    lat = loc.get("lat")
    lng = loc.get("lng")

    if lat is None or lng is None:
        # Try geocoding using MCP wrapper
        text = loc.get("text") or ""
        if text:
            geo = geocode_location(text)
            lat = geo.get("lat")
            lng = geo.get("lng")
            if lat is not None and lng is not None:
                loc.update({"lat": lat, "lng": lng, "formatted": geo.get("formatted")})

    if lat is None or lng is None:
        return {"hospitals": []}

    # Stage search by radius so we prioritize nearby facilities but still return options
    radius_steps = [5000, 10000, 20000]
    results = []
    radius_used = None
    for radius in radius_steps:
        try:
            found = find_nearby_hospitals(lat, lng, radius_m=radius)
        except Exception:
            found = []
        if found:
            results = found
            radius_used = radius
            break
    # Build diagnosis/symptom context for relevance ranking
    diagnosis_text = ""
    try:
        diagnoses = (state.get("diagnosis") or {}).get("diagnoses", [])
        if diagnoses:
            top = diagnoses[0]
            diagnosis_text = f"{top.get('disease', '')} {top.get('reason', '')}".lower()
    except Exception:
        diagnosis_text = ""
    symptom_text = " ".join((state.get("patient") or {}).get("symptoms", [])).lower()

    def _haversine_m(lat1, lon1, lat2, lon2):
        r = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    hospitals: List[Dict[str, Any]] = []
    for r in results[:40]:
        place_id = r.get("place_id")
        details = get_place_details(place_id) if place_id else {}
        # compute travel time if coordinates are available
        travel = {}
        try:
            if r.get("lat") is not None and r.get("lng") is not None:
                travel = get_travel_time(lat, lng, r.get("lat"), r.get("lng"))
        except Exception:
            travel = {}
        approx_distance = None
        try:
            if r.get("lat") is not None and r.get("lng") is not None:
                approx_distance = _haversine_m(lat, lng, float(r.get("lat")), float(r.get("lng")))
        except Exception:
            approx_distance = None

        name_text = (r.get("name") or "").lower()
        address_text = ((details.get("address") or r.get("address") or "")).lower()
        combined = f"{name_text} {address_text}"

        relevance = 0
        diagnosis_keywords = [k for k in diagnosis_text.replace("/", " ").split() if len(k) > 3]
        symptom_keywords = [k for k in symptom_text.replace("/", " ").split() if len(k) > 3]
        if any(k in combined for k in diagnosis_keywords):
            relevance += 3
        if any(k in combined for k in symptom_keywords):
            relevance += 2
        if "emergency" in combined or "trauma" in combined or "cardiac" in combined:
            relevance += 1

        hospitals.append({
            "name": r.get("name"),
            "address": details.get("address") or r.get("address"),
            "phone": details.get("phone"),
            "distance_m": travel.get("distance_m") or r.get("distance_m") or approx_distance,
            "travel_time_s": travel.get("duration_s"),
            "place_id": place_id,
            "relevance_score": relevance,
        })

    # Sort by relevance first, then distance
    hospitals_sorted = sorted(
        hospitals,
        key=lambda h: (-int(h.get("relevance_score") or 0), float(h.get("distance_m") or 1e12)),
    )

    # Return top 3 diagnosis-aligned + 2 nearest fallback (unique by place_id)
    aligned = [h for h in hospitals_sorted if int(h.get("relevance_score") or 0) > 0]
    top_relevant = aligned[:3]
    nearest_pool = sorted(hospitals, key=lambda h: float(h.get("distance_m") or 1e12))
    selected = []
    seen = set()
    for h in top_relevant:
        pid = h.get("place_id")
        if pid not in seen:
            selected.append(h)
            seen.add(pid)
    for h in nearest_pool:
        if len(selected) >= 5:
            break
        pid = h.get("place_id")
        if pid not in seen:
            selected.append(h)
            seen.add(pid)

    return {
        "hospitals": selected[:5],
        "hospital_search_meta": {
            "radius_used_m": radius_used,
            "aligned_count": len(top_relevant),
        },
    }
