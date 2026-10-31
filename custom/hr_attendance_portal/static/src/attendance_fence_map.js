/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const DEFAULT_CENTER = { lat: 10.8231, lng: 106.6297 };
const MAX_POINTS = 100;

function roundCoord(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
        return null;
    }
    return Math.round(number * 1e7) / 1e7;
}

export class AttendanceFenceMapField extends Component {
    static template = "hr_attendance_portal.AttendanceFenceMapField";
    static props = { ...standardFieldProps };

    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.markers = [];
        this.shape = null;
        this.fittedCount = null;
        this.state = useState({ mapError: "" });
        onWillStart(() => this.loadMaps());
        useEffect(
            () => {
                this.syncMap();
            },
            () => [this.pointsKey, this.apiKey, this.props.readonly, this.state.mapError]
        );
        onWillUnmount(() => this.destroyMap());
    }

    get apiKey() {
        return this.props.record.data.google_maps_api_key || "";
    }

    parseZones(raw) {
        if (!raw) {
            return [];
        }
        try {
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed) || !parsed.length) {
                return [];
            }
            if (parsed[0] && Object.prototype.hasOwnProperty.call(parsed[0], "latitude")) {
                return [{
                    name: "Zone 1",
                    points: parsed
                        .map((point) => ({
                            latitude: roundCoord(point.latitude),
                            longitude: roundCoord(point.longitude),
                        }))
                        .filter((point) => point.latitude !== null && point.longitude !== null),
                }];
            }
            return parsed.map((zone, index) => ({
                name: zone.name || `Zone ${index + 1}`,
                points: (zone.points || [])
                    .map((point) => ({
                        latitude: roundCoord(point.latitude),
                        longitude: roundCoord(point.longitude),
                    }))
                    .filter((point) => point.latitude !== null && point.longitude !== null),
            }));
        } catch {
            return [];
        }
    }

    get points() {
        const zones = this.parseZones(this.props.record.data[this.props.name]);
        return zones.length ? zones[0].points : [];
    }

    get pointsKey() {
        return JSON.stringify(this.points);
    }

    get statusText() {
        const zones = this.parseZones(this.props.record.data[this.props.name]);
        if (zones.length > 1) {
            return `Có ${zones.length} vùng đa giác. Chỉnh trong tab Polygon zones hoặc import CSV.`;
        }
        const count = this.points.length;
        if (!count) {
            return "Chưa có điểm. Chấm công dùng tâm và bán kính.";
        }
        if (count < 4) {
            return `Đã có ${count} điểm. Cần ít nhất 4 điểm để lưu vùng.`;
        }
        return `Đã có ${count} điểm. Có thể thêm vùng thứ hai bằng CSV (cùng tên workplace).`;
    }

    async loadMaps() {
        if (!this.apiKey || window.google?.maps) {
            return;
        }
        try {
            await loadJS(
                `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(this.apiKey)}&v=weekly`
            );
            if (!window.google?.maps) {
                this.state.mapError = "Không tải được Google Maps. Kiểm tra API key.";
            }
        } catch {
            this.state.mapError = "Không tải được Google Maps. Kiểm tra API key.";
        }
    }

    mapCenter() {
        const points = this.points;
        if (points.length) {
            return {
                lat: points.reduce((sum, point) => sum + point.latitude, 0) / points.length,
                lng: points.reduce((sum, point) => sum + point.longitude, 0) / points.length,
            };
        }
        const latitude = roundCoord(this.props.record.data.latitude);
        const longitude = roundCoord(this.props.record.data.longitude);
        if (latitude !== null && longitude !== null && (latitude || longitude)) {
            return { lat: latitude, lng: longitude };
        }
        return DEFAULT_CENTER;
    }

    syncMap() {
        const element = this.mapRef.el;
        if (!element || !window.google?.maps || this.state.mapError) {
            return;
        }
        if (!this.map) {
            this.map = new google.maps.Map(element, {
                center: this.mapCenter(),
                zoom: 17,
                mapTypeId: "hybrid",
                gestureHandling: "greedy",
                clickableIcons: false,
                streetViewControl: false,
            });
            this.map.addListener("click", (event) => this.onMapClick(event));
        }
        this.syncOverlays();
    }

    syncOverlays() {
        this.clearOverlays();
        const points = this.points;
        points.forEach((point, index) => {
            const marker = new google.maps.Marker({
                position: { lat: point.latitude, lng: point.longitude },
                map: this.map,
                draggable: !this.props.readonly,
                label: String(index + 1),
            });
            marker.addListener("dragend", () => {
                const next = this.points.slice();
                const position = marker.getPosition();
                next[index] = {
                    latitude: roundCoord(position.lat()),
                    longitude: roundCoord(position.lng()),
                };
                this.commit(next);
            });
            this.markers.push(marker);
        });
        if (points.length >= 2) {
            const path = points.map((point) => ({ lat: point.latitude, lng: point.longitude }));
            this.shape = points.length >= 3
                ? new google.maps.Polygon({
                    paths: path,
                    map: this.map,
                    strokeColor: "#1f6feb",
                    strokeWeight: 2,
                    fillColor: "#1f6feb",
                    fillOpacity: 0.25,
                })
                : new google.maps.Polyline({
                    path,
                    map: this.map,
                    strokeColor: "#1f6feb",
                    strokeWeight: 2,
                });
        }
        if (this.fittedCount !== points.length) {
            this.fitPoints(points);
            this.fittedCount = points.length;
        }
    }

    fitPoints(points) {
        if (!points.length) {
            this.map.setCenter(this.mapCenter());
            this.map.setZoom(17);
            return;
        }
        const bounds = new google.maps.LatLngBounds();
        for (const point of points) {
            bounds.extend({ lat: point.latitude, lng: point.longitude });
        }
        if (points.length === 1) {
            this.map.setCenter(bounds.getCenter());
            this.map.setZoom(17);
            return;
        }
        this.map.fitBounds(bounds, 48);
    }

    onMapClick(event) {
        if (this.props.readonly || this.points.length >= MAX_POINTS) {
            return;
        }
        this.commit(this.points.concat([{
            latitude: roundCoord(event.latLng.lat()),
            longitude: roundCoord(event.latLng.lng()),
        }]));
    }

    commit(points) {
        const values = {
            [this.props.name]: JSON.stringify([{
                name: "Zone 1",
                points,
            }]),
        };
        if (points.length >= 4) {
            values.latitude = roundCoord(
                points.reduce((sum, point) => sum + point.latitude, 0) / points.length
            );
            values.longitude = roundCoord(
                points.reduce((sum, point) => sum + point.longitude, 0) / points.length
            );
        }
        this.props.record.update(values);
    }

    undoPoint() {
        if (!this.points.length) {
            return;
        }
        this.commit(this.points.slice(0, -1));
    }

    clearPoints() {
        this.commit([]);
    }

    addManualPoint() {
        if (this.points.length >= MAX_POINTS) {
            return;
        }
        const last = this.points[this.points.length - 1];
        const center = this.mapCenter();
        this.commit(this.points.concat([{
            latitude: last ? last.latitude : roundCoord(center.lat),
            longitude: last ? last.longitude : roundCoord(center.lng),
        }]));
    }

    updatePoint(index, key, value) {
        const coordinate = roundCoord(value);
        if (coordinate === null) {
            return;
        }
        const points = this.points.map((point, pointIndex) => (
            pointIndex === index ? { ...point, [key]: coordinate } : point
        ));
        this.commit(points);
    }

    removePoint(index) {
        const points = this.points.slice();
        points.splice(index, 1);
        this.commit(points);
    }

    clearOverlays() {
        for (const marker of this.markers) {
            marker.setMap(null);
        }
        this.markers = [];
        if (this.shape) {
            this.shape.setMap(null);
            this.shape = null;
        }
    }

    destroyMap() {
        this.clearOverlays();
        if (this.map && window.google?.maps) {
            google.maps.event.clearInstanceListeners(this.map);
        }
        this.map = null;
    }
}

registry.category("fields").add("attendance_fence_map", {
    component: AttendanceFenceMapField,
    supportedTypes: ["text", "char"],
});
