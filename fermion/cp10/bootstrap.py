from ._core import bootstrap
import numpy as np
def ci(values,raw): return np.quantile(bootstrap(values,raw),[.025,.975],method="linear")

