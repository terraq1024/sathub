import { forwardRef, useEffect } from 'react';
import type { LatLngBoundsExpression, TileLayer as LeafletTileLayer } from 'leaflet';
import { TileLayer, useMap } from 'react-leaflet';

export type TianDiTuMapType = 'vec' | 'img';

const tianDiTuToken = import.meta.env.VITE_TIANDITU_TOKEN;
const tianDiTuSubdomains = ['t0', 't1', 't2', 't3', 't4', 't5', 't6', 't7'];
const tianDiTuUrls = {
  vec: 'https://{s}.tianditu.gov.cn/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=' + (tianDiTuToken ?? ''),
  vecLabel: 'https://{s}.tianditu.gov.cn/cva_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=cva&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=' + (tianDiTuToken ?? ''),
  img: 'https://{s}.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=' + (tianDiTuToken ?? ''),
  imgLabel: 'https://{s}.tianditu.gov.cn/cia_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=cia&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=' + (tianDiTuToken ?? '')
};

export const BaseMapLayer = forwardRef<LeafletTileLayer>(function BaseMapLayer(_props, ref) {
  return (
    <TileLayer
      ref={ref}
      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    />
  );
});

export function TianDiTuLayer({ mapType = 'vec' }: { mapType?: TianDiTuMapType }) {
  if (!tianDiTuToken) return <BaseMapLayer />;
  const labelUrl = mapType === 'img' ? tianDiTuUrls.imgLabel : tianDiTuUrls.vecLabel;
  return (
    <>
      <TileLayer
        key={mapType}
        attribution="&copy; 天地图"
        url={tianDiTuUrls[mapType]}
        subdomains={tianDiTuSubdomains}
        maxZoom={18}
      />
      <TileLayer
        key={`${mapType}-label`}
        attribution="&copy; 天地图"
        url={labelUrl}
        subdomains={tianDiTuSubdomains}
        maxZoom={18}
        pane="overlayPane"
      />
    </>
  );
}

export function FitBounds({ bounds, maxZoom = 15 }: { bounds?: LatLngBoundsExpression; maxZoom?: number }) {
  const map = useMap();
  useEffect(() => {
    if (!bounds) return;
    const fit = () => map.fitBounds(bounds, { padding: [24, 24], maxZoom });
    fit();
    const timer = window.setTimeout(fit, 160);
    return () => window.clearTimeout(timer);
  }, [bounds, map, maxZoom]);
  return null;
}

export function RefreshMapSize({ trigger }: { trigger?: unknown }) {
  const map = useMap();
  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 80);
    return () => window.clearTimeout(timer);
  }, [map, trigger]);
  return null;
}
