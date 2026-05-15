select
    sum(l_extendedprice) / 7.0 as avg_yearly
from
    lineitem,
    part