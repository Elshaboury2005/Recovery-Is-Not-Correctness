import pandas as pd
import pytest
from app.pipeline.filter_expression import validate_filter_condition, pandas_filter_condition
from app.plugins.processors.filter_processor import FilterProcessor

def test_sql_equality_is_valid_and_executable():
    validate_filter_condition("status = 'active'")
    result=FilterProcessor().process(pd.DataFrame({'status':['active','inactive']}),{'condition':"status = 'active'"})
    assert result['status'].tolist()==['active']

def test_literal_equality_is_not_rewritten():
    assert pandas_filter_condition("status = 'x=y'")=="status == 'x=y'"

@pytest.mark.parametrize('condition',["'='", "'amount > 0'", "   "])
def test_literal_operator_is_not_comparison(condition):
    with pytest.raises(ValueError): validate_filter_condition(condition)

def test_whitespace_and_boolean_case():
    result=FilterProcessor().process(pd.DataFrame({'a':[1,2,3]}),{'condition':'  a = 1 OR a = 3  '})
    assert result['a'].tolist()==[1,3]
