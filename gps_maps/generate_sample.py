import math
from gps_maps.utm_converter import UTMConverter

def calc_chk(s):
    c = 0
    for char in s:
        c ^= ord(char)
    return f"{c:02X}"

start_lat = -7.7700
start_lon = 110.3700
electrodes = UTMConverter.generate_linear_survey(start_lat, start_lon, azimuth_deg=45.0, spacing_m=5.0, num_electrodes=32)

nmea_lines = []
for i, el in enumerate(electrodes):
    lat = el['latitude']
    lon = el['longitude']
    
    lat_deg = int(abs(lat))
    lat_min = (abs(lat) - lat_deg) * 60.0
    lat_dir = 'S' if lat < 0 else 'N'
    lat_str = f"{lat_deg:02d}{lat_min:07.4f}"
    
    lon_deg = int(abs(lon))
    lon_min = (abs(lon) - lon_deg) * 60.0
    lon_dir = 'W' if lon < 0 else 'E'
    lon_str = f"{lon_deg:03d}{lon_min:07.4f}"
    
    utc_sec = 10 * i
    utc_h = (utc_sec // 3600) + 8
    utc_m = (utc_sec % 3600) // 60
    utc_s = utc_sec % 60
    utc_str = f"{utc_h:02d}{utc_m:02d}{utc_s:02d}.00"
    
    alt = round(120.0 + 3.0 * math.sin(i / 5.0) + (i * 0.15), 2)
    
    body = f"GPGGA,{utc_str},{lat_str},{lat_dir},{lon_str},{lon_dir},4,14,0.8,{alt:.1f},M,-23.4,M,1.0,0001"
    chk = calc_chk(body)
    nmea_lines.append(f"${body}*{chk}")

with open('/home/localai/projects/resipy-web-platform/gps_maps/sample_survey_gga.nmea', 'w', encoding='utf-8') as f:
    f.write('\n'.join(nmea_lines) + '\n')

print(f"Regenerated {len(nmea_lines)} NMEA sentences successfully.")
