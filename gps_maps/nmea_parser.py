"""
NMEA-0183 ($GPGGA / $GNGGA) Parser for Geophysics Field Telemetry.
Parses field GPS logs from ESP32, Garmin, and GNSS RTK receivers.
"""

from typing import Dict, List, Optional, Any
import re

class NMEAParser:
    def __init__(self):
        pass

    @staticmethod
    def verify_checksum(sentence: str) -> bool:
        """Validates NMEA sentence XOR checksum (*hh)."""
        sentence = sentence.strip()
        if not sentence.startswith('$') or '*' not in sentence:
            return False
        
        data_part, chk = sentence[1:].rsplit('*', 1)
        if len(chk) != 2:
            return False
        
        expected = 0
        for char in data_part:
            expected ^= ord(char)
        
        try:
            return expected == int(chk, 16)
        except ValueError:
            return False

    @staticmethod
    def parse_lat_lon(raw_val: str, direction: str, is_lon: bool = False) -> Optional[float]:
        """Converts DDMM.MMMM or DDDMM.MMMM to decimal degrees."""
        if not raw_val or not direction:
            return None
        
        try:
            deg_len = 3 if is_lon else 2
            deg = float(raw_val[:deg_len])
            minutes = float(raw_val[deg_len:])
            dec = deg + (minutes / 60.0)
            if direction.upper() in ['S', 'W']:
                dec = -dec
            return dec
        except (ValueError, IndexError):
            return None

    @classmethod
    def parse_gga(cls, sentence: str) -> Optional[Dict[str, Any]]:
        """
        Parses $GPGGA / $GNGGA sentence into structured dictionary.
        Format:
        $GPGGA,hhmmss.ss,llll.ll,a,yyyyy.yy,a,x,xx,x.x,x.x,M,x.x,M,x.x,xxxx*hh
        """
        sentence = sentence.strip()
        if not (sentence.startswith('$GPGGA') or sentence.startswith('$GNGGA')):
            return None
        
        # Checksum validation if present
        if '*' in sentence and not cls.verify_checksum(sentence):
            return None

        # Clean sentence
        raw = sentence.split('*')[0]
        parts = raw.split(',')
        if len(parts) < 10:
            return None

        utc_time = parts[1]
        lat_raw, lat_dir = parts[2], parts[3]
        lon_raw, lon_dir = parts[4], parts[5]
        fix_quality = parts[6]
        num_sats = parts[7]
        hdop = parts[8]
        altitude = parts[9]
        geoid_sep = parts[11] if len(parts) > 11 else ""

        fix_desc = {
            '0': 'Invalid / No Fix',
            '1': 'GPS SPS (Autonomous)',
            '2': 'DGPS Fix',
            '3': 'PPS Fix',
            '4': 'RTK Fixed',
            '5': 'RTK Float',
            '6': 'Estimated / Dead Reckoning'
        }

        lat = cls.parse_lat_lon(lat_raw, lat_dir, is_lon=False)
        lon = cls.parse_lat_lon(lon_raw, lon_dir, is_lon=True)
        if lat is None or lon is None:
            return None

        try:
            alt_val = float(altitude) if altitude else 0.0
            sats_val = int(num_sats) if num_sats else 0
            hdop_val = float(hdop) if hdop else 99.9
            fix_val = int(fix_quality) if fix_quality else 0
            geoid_val = float(geoid_sep) if geoid_sep else 0.0
        except ValueError:
            return None

        # Format UTC timestamp hh:mm:ss
        formatted_time = ""
        if len(utc_time) >= 6:
            formatted_time = f"{utc_time[0:2]}:{utc_time[2:4]}:{utc_time[4:6]}"

        return {
            "sentence": parts[0][1:],
            "utc_time": formatted_time,
            "raw_time": utc_time,
            "latitude": round(lat, 7),
            "longitude": round(lon, 7),
            "fix_quality": fix_val,
            "fix_description": fix_desc.get(str(fix_val), "Unknown"),
            "satellites": sats_val,
            "hdop": hdop_val,
            "altitude_m": round(alt_val, 2),
            "geoid_separation_m": round(geoid_val, 2)
        }

    @classmethod
    def parse_stream(cls, text: str) -> List[Dict[str, Any]]:
        """Parses multi-line NMEA logs and returns list of valid GGA fixes."""
        records = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                parsed = cls.parse_gga(line)
                if parsed and parsed["fix_quality"] > 0:
                    records.append(parsed)
        return records
