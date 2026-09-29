from app.models import RENDERERS

def test_only_supported_renderers_are_exposed():
    assert set(RENDERERS)=={"ltx25","skyreelsv3"}
    assert list(RENDERERS["ltx25"].supported_durations)==list(range(4,11))
    assert RENDERERS["ltx25"].supports_end_frame is True
    assert RENDERERS["skyreelsv3"].supported_durations==[5]
