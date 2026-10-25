import pytest
import trimesh

import acousticfem as af
from acousticfem import geometry


def l_shaped_room():
    a = trimesh.creation.box(extents=[8, 6, 3.5])
    a.apply_translation([4, 3, 1.75])
    b = trimesh.creation.box(extents=[4, 3, 3.5])
    b.apply_translation([6, 4.5, 1.75])
    return a.difference(b)


def test_box_surfaces():
    room = af.box(8, 6, 3.5, 1.0)
    assert room.volume == pytest.approx(168)
    assert room.surface_area("floor") == pytest.approx(48)
    assert room.surface_area("x0") == pytest.approx(21)
    assert room.surface_area() == pytest.approx(194)


@pytest.mark.parametrize("mesher", ["gmsh", "tetwild"])
def test_real_geometry_is_meshed_not_its_bounding_box(mesher):
    surface = l_shaped_room()
    room = geometry.from_surface(surface, 0.8, mesher=mesher)
    assert room.volume == pytest.approx(126, rel=0.005)  # the bounding box is 168
    areas = room.areas()
    assert areas["floor"] == pytest.approx(36, rel=0.01)
    assert areas["ceiling"] == pytest.approx(36, rel=0.01)
    assert sum(areas.values()) == pytest.approx(surface.area, rel=0.01)


def test_surface_areas_before_meshing():
    areas = geometry.surface_areas(l_shaped_room())
    assert areas == pytest.approx({"floor": 36, "ceiling": 36, "walls": 98})


def test_load_surface_drops_debris_and_fixes_orientation(tmp_path):
    room = trimesh.creation.box(extents=[4, 3, 2.5])
    room.invert()
    debris = trimesh.creation.box(extents=[0.05, 0.05, 0.05])
    debris.apply_translation([10, 10, 10])
    path = tmp_path / "scan.stl"
    trimesh.util.concatenate([room, debris]).export(path)
    surface = geometry.load_surface(path)
    assert surface.volume == pytest.approx(30)


def test_open_surface_is_rejected(tmp_path):
    # A room without its ceiling (trimesh closes holes of a single triangle by itself)
    room = trimesh.creation.box(extents=[4, 3, 2.5]).subdivide().subdivide()
    room.update_faces(room.triangles_center[:, 2] < 1.2)
    room.remove_unreferenced_vertices()
    path = tmp_path / "open.stl"
    room.export(path)
    with pytest.raises(ValueError, match="not a closed surface"):
        geometry.load_surface(path)
