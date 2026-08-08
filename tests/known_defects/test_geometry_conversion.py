import numpy as np
import pytest
import trimesh

from mesh.converter import trimesh_to_fenicsx


class BoundingBoxSubstitutionDefect(AssertionError):
    """The converted sphere is the current axis-aligned bounding box."""


@pytest.mark.integration
@pytest.mark.known_defect
@pytest.mark.xfail(
    raises=BoundingBoxSubstitutionDefect,
    strict=True,
    reason="trimesh_to_fenicsx currently replaces input geometry with its bounding box",
)
def test_sphere_conversion_does_not_create_box_corner_vertices():
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    assert sphere.is_watertight
    domain = trimesh_to_fenicsx(sphere)

    coordinates = domain.geometry.x
    assert coordinates.ndim == 2 and coordinates.shape[1] == 3
    assert len(coordinates) > 0
    assert np.isfinite(coordinates).all()
    maximum_radius = np.linalg.norm(coordinates, axis=1).max()
    has_unit_box_corner = np.any(
        np.all(np.isclose(np.abs(coordinates), 1.0, atol=1e-12), axis=1)
    )
    if has_unit_box_corner and maximum_radius == pytest.approx(np.sqrt(3.0)):
        raise BoundingBoxSubstitutionDefect(
            "unit sphere was replaced by the [-1, 1]^3 bounding box"
        )

    assert maximum_radius <= 1.01
