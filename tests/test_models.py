from app.models import RENDERERS

def test_three_renderers():
    assert set(RENDERERS)=={"ltx25","wan22","skyreelsv3"}
    assert list(RENDERERS["ltx25"].supported_durations)==list(range(4,11))
    assert RENDERERS["ltx25"].supports_end_frame is True
    assert RENDERERS["skyreelsv3"].supported_durations==[5]
