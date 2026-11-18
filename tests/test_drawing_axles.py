import pytest

from liftcalc.drawing.body import WHEEL_R, drawing_axles
from liftcalc.drawing.figures import elevation_figure
from liftcalc.drawing.primitives import Circle, Image
from liftcalc.core.result import ComputationResult


@pytest.mark.parametrize('tonnage,expected',[(70,4),(100,4),(101,6),(130,6),(150,6),(200,6),(299,6),(300,8),(500,8)])
def test_wheels_on_actual_sheet(tonnage,expected):
    cap = dict(ok=True, mode='single', model='图元测试', tonnage_class=tonnage,
               required=10,limit=.9,max_radius=10,boom_len=25.98,boom_angle=67.6,lift_height=24.43,
               rated_load=15.5,utilization=.7)
    result=ComputationResult(kind='crane.capability',engine_version='test',aux={'capability':cap})
    sheet=elevation_figure(result)
    assert sheet.meta['axles']==expected
    wheels=[item for item in sheet.primitives if isinstance(item,Circle) and item.layer=='OUTLINE' and
            abs(item.r-WHEEL_R*sheet.meta['scale'])<1e-8]
    assert len({round(item.cx,6) for item in wheels if item.cy==min(wheel.cy for wheel in wheels)})==expected
    assert not any(isinstance(item,Image) for item in sheet.primitives)


def test_legacy_result_uses_catalog_not_payload():
    assert drawing_axles({'model':'QY70K-1','required':300},{},'徐工')==4
    assert drawing_axles({'model':'QAY200','required':1},{},'徐工')==6
    assert drawing_axles({'model':'未知型号','required':500},{},'徐工') is None
