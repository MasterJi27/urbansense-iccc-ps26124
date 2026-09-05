from app.geo import bounding_box, haversine_m, validate_coords


def test_bounding_box_keeps_40m_neighbour():
    lat, lon = 28.6328, 77.2195
    lat_min, lat_max, lon_min, lon_max = bounding_box(lat, lon, 60)
    near_lat, near_lon = 28.6329, 77.2196
    assert lat_min <= near_lat <= lat_max
    assert lon_min <= near_lon <= lon_max
    assert haversine_m(lat, lon, near_lat, near_lon) < 40


def test_bounding_box_excludes_other_city():
    lat_min, lat_max, lon_min, lon_max = bounding_box(28.6328, 77.2195, 60)
    assert not (lat_min <= 19.07 <= lat_max and lon_min <= 72.87 <= lon_max)


def test_validate_coords_rejects_out_of_range():
    try:
        validate_coords(100, 77)
        raised = False
    except ValueError:
        raised = True
    assert raised
