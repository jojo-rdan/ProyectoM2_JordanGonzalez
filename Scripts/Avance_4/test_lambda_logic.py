import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lambda_functions.delivery_logic import check_delivery_completed,estimate_eta,detect_route_deviation,validate_event

sample={'event_id':'ev-demo-1','delivery_id':101,'event_type':'delivery_status',
        'status':'delivered','occurred_at':'2026-11-17T14:00:00Z'}
assert check_delivery_completed(sample)['completed'] is True
assert validate_event(sample)['event_id']=='ev-demo-1'
assert estimate_eta({'remaining_distance_km':10,'average_speed_kmh':40})['estimated_minutes']==15
assert detect_route_deviation({'current_position':{'lat':4.71,'lon':-74.07},
                               'expected_waypoint':{'lat':4.71,'lon':-74.07}})['alert'] is False
print('AVANCE 4: cuatro funciones de demostracion OK, sin AWS')
