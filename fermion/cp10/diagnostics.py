from ._core import Stats
import numpy as np
def finite(*a): return all(np.all(np.isfinite(x)) and np.max(np.abs(x))<=1e6 for x in a)
def production_margin(space,time):
 if not all(np.isfinite([space,time])): raise RuntimeError("missing production error")
 return max(.01,3*(space+time))
def h2_margin(fs,ft,os,ot):
 if not all(np.isfinite([fs,ft,os,ot])): raise RuntimeError("missing H2 production error")
 return max(.01,3*(fs+ft+os+ot))

