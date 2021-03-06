"""
Example on retrieving and plotting winds
----------------------------------------

This is a simple example for how to retrieve and plot winds from 2 radars
using PyDDA.

Author: Robert C. Jackson

"""

import pyart
import pydda
from matplotlib import pyplot as plt
import numpy as np


berr_grid = pyart.io.read_grid("/home/rjackson/data/berr_Darwin_hires.nc")
cpol_grid = pyart.io.read_grid("/home/rjackson/data/cpol_Darwin_hires.nc")

sounding = pyart.io.read_arm_sonde(
    "/home/rjackson/data/soundings/twpsondewnpnC3.b1.20060119.231600.custom.cdf")


# Load sounding data and insert as an intialization
u_init, v_init, w_init = pydda.initialization.make_wind_field_from_profile(
        cpol_grid, sounding, vel_field='VT')

# Start the wind retrieval. This example only uses the mass continuity
# and data weighting constraints.
Grids = pydda.retrieval.get_dd_wind_field([berr_grid, cpol_grid], u_init,
                                          v_init, w_init, Co=10.0, Cm=1500.0, 
                                          Cz=0, vel_name='VT', refl_field='DT',
                                          frz=5000.0, filt_iterations=2, 
                                          mask_outside_opt=True, upper_bc=1)
# Plot a horizontal cross section
plt.figure(figsize=(9,9))
pydda.vis.plot_horiz_xsection_barbs(Grids, background_field='DT', level=6,
                                    w_vel_contours=[3, 6, 9, 12, 15],
                                    barb_spacing_x_km=5.0,
                                    barb_spacing_y_km=15.0)

# Plot a vertical X-Z cross section
plt.figure(figsize=(9,9))
pydda.vis.plot_xz_xsection_barbs(Grids, background_field='DT', level=40,
                                 w_vel_contours=[3, 6, 9, 12, 15],
                                 barb_spacing_x_km=10.0,
                                 barb_spacing_z_km=2.0)

# Plot a vertical Y-Z cross section
plt.figure(figsize=(9,9))
pydda.vis.plot_yz_xsection_barbs(Grids, background_field='DT', level=40,
                                 w_vel_contours=[3, 6, 9, 12, 15],
                                 barb_spacing_x_km=10.0,
                                 barb_spacing_z_km=2.0)
