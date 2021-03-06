"""
===========================
pydda.vis (pydda.vis)
===========================

.. currentmodule:: pydda.vis

A visualization module for plotting generated wind fields.

.. autosummary::
    :toctree: generated/
  
    plot_horiz_xsection_barbs
    plot_xz_xsection_barbs
    plot_yz_xsection_barbs
    plot_horiz_xsection_streamlines
    plot_xz_xsection_streamlines
    plot_yz_xsection_streamlines

"""


from .barb_plot import plot_horiz_xsection_barbs, plot_xz_xsection_barbs
from .barb_plot import plot_yz_xsection_barbs
from .streamline_plot import plot_horiz_xsection_streamlines
from .streamline_plot import plot_xz_xsection_streamlines
from .streamline_plot import plot_yz_xsection_streamlines


