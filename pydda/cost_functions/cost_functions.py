"""
Created on Wed Jul 19 11:31:02 2017

@author: rjackson
"""

import numpy as np
import pyart

from numba import jit, cuda
from numba import vectorize
import scipy.ndimage.filters

 
def J_function(winds, vrs, azs, els, wts, u_back, v_back,
               Co, Cm, Cx, Cy, Cz, Cb, Cv, Ut, Vt, grid_shape,
               dx, dy, dz, z, rmsVr, weights, bg_weights, upper_bc,
               print_out=False):
    """
    Calculates the cost function.
    
    Parameters
    ----------
    winds: 1-D float array
        The wind field, flattened to 1-D for f_min
    vrs: List of float arrays
        List of radial velocities from each radar    
    azs: List of float arrays
        List of azimuths from each radar
    els: List of float arrays
        List of elevations from each radar    
    wts: List of float arrays
        Float array containing fall speed from radar.
    u_back: 1D float array (number of vertical levels):
        Background u wind
    v_back: 1D float array (number of vertical levels):
        Background u wind    
    Co: float
        Weighting coefficient for data constraint.
    Cm: float
        Weighting coefficient for mass continuity constraint.
    Cx: float
        Smoothing coefficient for x-direction
    Cy: float
        Smoothing coefficient for y-direction
    Cz: float
        Smoothing coefficient for z-direction
    Cb: float
        Coefficient for sounding constraint
    Cv: float
        Weight for cost function related to vertical vorticity equation.
    Ut: float
        Prescribed storm motion. This is only needed if Cv is not zero.
    Vt: float
        Prescribed storm motion. This is only needed if Cv is not zero.  
    grid_shape:
        Shape of wind grid
    dx:
        Spacing of grid in x direction
    dy:
        Spacing of grid in y direction
    dz:
        Spacing of grid in z direction
    z:
        Grid vertical levels in m
    rmsVr: float
        The sum of squares of velocity/num_points. Use for normalization
        of data weighting coefficient
    weights: n_radars x_bins x y_bins float array
        Data weights for each pair of radars
    bg_weights: z_bins x x_bins x y_bins float array
        Data weights for sounding constraint
    upper_bc: bool
        True to enforce w=0 at top of domain (impermeability condition),
        False to not enforce impermeability at top of domain
    print_out: bool
        Set to True to print out the value of the cost function.
        
    Returns
    -------
    J: float
        The value of the cost function
    """
    winds = np.reshape(winds, (3, grid_shape[0], grid_shape[1],
                                  grid_shape[2]))
      
    Jvel = calculate_radial_vel_cost_function(vrs, azs, els, winds[0],
                                              winds[1], winds[2], wts,
                                              rmsVr=rmsVr, weights=weights,
                                              coeff=Co)
    if(Cm > 0):
        Jmass = calculate_mass_continuity(
            winds[0], winds[1], winds[2], z, dx, dy, dz, coeff=Cm)
    else:
        Jmass = 0
          
    if(Cx > 0 or Cy > 0 or Cz > 0):
        Jsmooth = calculate_smoothness_cost(
            winds[0], winds[1], winds[2], Cx=Cx, Cy=Cy, Cz=Cz)
    else:
        Jsmooth = 0
        
    if(Cb > 0):
        Jbackground = calculate_background_cost(
            winds[0], winds[1], winds[2], bg_weights, u_back, v_back, Cb)
    else:
        Jbackground = 0
        
    if(Cv > 0):
        Jvorticity =  calculate_vertical_vorticity_cost(winds[0], winds[1],
                                                        winds[2], dx, dy, 
                                                        dz, Ut, Vt, 
                                                        coeff=Cv)
    else:
        Jvorticity = 0
        
    if(print_out==True):
        print('| Jvel    | Jmass   | Jsmooth |   Jbg   | Jvort   | Max w  ')
        print(('|' + "{:9.4f}".format(Jvel) + '|' + 
               "{:9.4f}".format(Jmass) + '|' + 
               "{:9.4f}".format(Jsmooth) + '|' + 
               "{:9.4f}".format(Jbackground) + '|' + 
               "{:9.4f}".format(Jvorticity) + '|' +
               "{:9.4f}".format(np.abs(winds[2]).max())))
           

    return Jvel + Jmass + Jsmooth + Jbackground + Jvorticity

    
def grad_J(winds, vrs, azs, els, wts, u_back, v_back, Co, Cm, Cx, Cy, 
           Cz, Cb, Cv, Ut, Vt, grid_shape, dx, dy, dz, z, rmsVr, 
           weights, bg_weights, upper_bc, print_out=False):
    """
    Calculates the gradient of the cost function.
    
    Parameters
    ----------
    winds: 1-D float array
        The wind field, flattened to 1-D for f_min
    vrs: List of float arrays
        List of radial velocities from each radar    
    azs: List of float arrays
        List of azimuths from each radar
    els: List of float arrays
        List of elevations from each radar    
    wts: List of float arrays
        Float array containing fall speed from radar.
    u_back: 1D float array (number of vertical levels):
        Background u wind
    v_back: 1D float array (number of vertical levels):
        Background u wind    
    Co: float
        Weighting coefficient for data constraint.
    Cm: float
        Weighting coefficient for mass continuity constraint.
    Cx: float
        Smoothing coefficient for x-direction
    Cy: float
        Smoothing coefficient for y-direction
    Cz: float
        Smoothing coefficient for z-direction
    Cb: float
        Coefficient for sounding constraint
    Cv: float
        Weight for cost function related to vertical vorticity equation.
    Ut: float
        Prescribed storm motion. This is only needed if Cv is not zero.
    Vt: float
        Prescribed storm motion. This is only needed if Cv is not zero.  
    grid_shape:
        Shape of wind grid
    dx:
        Spacing of grid in x direction
    dy:
        Spacing of grid in y direction
    dz:
        Spacing of grid in z direction
    z:
        Grid vertical levels in m
    rmsVr: float
        The sum of squares of velocity/num_points. Use for normalization
        of data weighting coefficient
    weights: n_radars x_bins x y_bins float array
        Data weights for each pair of radars
    bg_weights: z_bins x x_bins x y_bins float array
        Data weights for sounding constraint
    upper_bc: bool
        True to enforce w=0 at top of domain (impermeability condition),
        False to not enforce impermeability at top of domain
        
    Returns
    -------
    grad: 1D float array
        Gradient vector of cost function
    """ 
    winds = np.reshape(winds, (3, grid_shape[0], grid_shape[1],
                                      grid_shape[2]))
    grad = calculate_grad_radial_vel(
        vrs, els, azs, winds[0], winds[1], winds[2], wts, weights,
        rmsVr, coeff=Co, upper_bc=upper_bc)
    
    if(Cm > 0):
        grad += calculate_mass_continuity_gradient(
            winds[0], winds[1], winds[2], z, dx, dy, dz, coeff=Cm, 
            upper_bc=upper_bc)
                                                                    
    if(Cx > 0 or Cy > 0 or Cz > 0):
        grad += calculate_smoothness_gradient(
            winds[0], winds[1], winds[2], Cx=Cx, Cy=Cy, Cz=Cz, 
            upper_bc=upper_bc)
        
    if(Cb > 0):
        grad += calculate_background_gradient(
            winds[0], winds[1], winds[2], bg_weights, u_back, v_back, Cb,
            upper_bc=upper_bc)
    if(Cv > 0):
        grad += calculate_vertical_vorticity_gradient(winds[0], winds[1], 
                                                      winds[2], dx, dy, 
                                                      dz, Ut, Vt, 
                                                      coeff=Cv)    
        
    if(print_out==True):    
        print('Norm of gradient: ' + str(np.linalg.norm(grad, np.inf)))
    return grad


def calculate_radial_vel_cost_function(vrs, azs, els, u, v,
                                       w, wts, rmsVr, weights, coeff=1.0,
                                       ):
    """
    Calculates the cost function due to difference of the wind field from
    radar radial velocities. 
    
    All grids must have the same grid specification.
    
    Parameters
    ----------
    vrs: List of float arrays
        List of radial velocities from each radar
    els: List of float arrays
        List of elevations from each radar
    azs: List of float arrays
        List of azimuths from each radar
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    wts: List of float arrays
        Float array containing fall speed from radar.
    rmsVr: float
        The sum of squares of velocity/num_points. Use for normalization
        of data weighting coefficient
    weights: n_radars x_bins x y_bins float array
        Data weights for each pair of radars
    coeff: float
        Constant for cost function  
    
    Returns
    -------
    J_o: float
         Observational cost function
    """
         
    J_o = 0
    lambda_o = coeff / (rmsVr * rmsVr)
    for i in range(len(vrs)):
        v_ar = (np.cos(els[i])*np.sin(azs[i])*u +
                np.cos(els[i])*np.cos(azs[i])*v +
                np.sin(els[i])*(w - np.abs(wts[i])))
        the_weight = weights[i]
        the_weight[els[i].mask == True] = 0
        the_weight[azs[i].mask == True] = 0
        the_weight[vrs[i].mask == True] = 0
        the_weight[wts[i].mask == True] = 0
        J_o += lambda_o*np.sum(np.square(vrs[i]-v_ar)*the_weight)
    
    return J_o


def calculate_grad_radial_vel(vrs, els, azs, u, v, w,
                              wts, weights, rmsVr, coeff=1.0, upper_bc=True):
    """
    Calculates the gradient of the cost function due to difference of wind field from
    radar radial velocities. 

    All grids must have the same grid specification.
    
    Parameters
    ----------
    vrs: List of float arrays
        List of radial velocities from each radar
    els: List of float arrays
        List of elevations from each radar
    azs: List of azimuths
        List of azimuths from each radar
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    coeff: float
        Constant for cost function
    dudt: float
        Background storm motion
    dvdt: float
        Background storm motion
    vel_name: str
        Background velocity field name
    weights: n_radars x_bins x y_bins float array
        Data weights for each pair of radars
    
    Returns
    -------
    y: 1-D float array 
         Gradient vector of observational cost function    
    """
    
    # Use zero for all masked values since we don't want to add them into
    # the cost function
    
    p_x1 = np.zeros(vrs[1].shape)
    p_y1 = np.zeros(vrs[1].shape)
    p_z1 = np.zeros(vrs[1].shape)
    lambda_o = coeff / (rmsVr * rmsVr)
    
    for i in range(len(vrs)):
        v_ar = (np.cos(els[i])*np.sin(azs[i])*u +
            np.cos(els[i])*np.cos(azs[i])*v +
            np.sin(els[i])*(w - np.abs(wts[i])))
            
        x_grad = (2*(v_ar - vrs[i])*np.cos(els[i])*np.sin(azs[i])*weights[i])*lambda_o
        y_grad = (2*(v_ar - vrs[i])*np.cos(els[i])*np.cos(azs[i])*weights[i])*lambda_o
        z_grad = (2*(v_ar - vrs[i])*np.sin(els[i])*weights[i])*lambda_o
    
        x_grad[els[i].mask == True] = 0
        y_grad[els[i].mask == True] = 0
        z_grad[els[i].mask == True] = 0
        x_grad[azs[i].mask == True] = 0
        y_grad[azs[i].mask == True] = 0
        z_grad[azs[i].mask == True] = 0
        
        x_grad[els[i].mask == True] = 0
        x_grad[azs[i].mask == True] = 0
        x_grad[vrs[i].mask == True] = 0
        x_grad[wts[i].mask == True] = 0
        y_grad[els[i].mask == True] = 0
        y_grad[azs[i].mask == True] = 0
        y_grad[vrs[i].mask == True] = 0
        y_grad[wts[i].mask == True] = 0
        z_grad[els[i].mask == True] = 0
        z_grad[azs[i].mask == True] = 0
        z_grad[vrs[i].mask == True] = 0
        z_grad[wts[i].mask == True] = 0
        
        p_x1 += x_grad
        p_y1 += y_grad
        p_z1 += z_grad
    # Impermeability condition
    p_z1[0, :, :] = 0
    if(upper_bc == True):
        p_z1[-1, :, :] = 0
    y = np.stack((p_x1, p_y1, p_z1), axis=0)
    return y.flatten()


def calculate_smoothness_cost(u, v, w, Cx=1e-5, Cy=1e-5, Cz=1e-5):
    """
    Calculates the smoothness cost function by taking the Laplacian of the
    wind field. 

    All grids must have the same grid specification. 
    
    Parameters
    ----------
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    Cx: float
        Constant controlling smoothness in x-direction
    Cy: float
        Constant controlling smoothness in y-direction
    Cz: float
        Constant controlling smoothness in z-direction
    
    Returns
    -------
    Js: float
        value of smoothness cost function
    """
    du = np.zeros(w.shape)
    dv = np.zeros(w.shape)
    dw = np.zeros(w.shape)
    scipy.ndimage.filters.laplace(u,du, mode='wrap')
    scipy.ndimage.filters.laplace(v,dv, mode='wrap')
    scipy.ndimage.filters.laplace(w,dw, mode='wrap')
    return np.sum(Cx*du**2 + Cy*dv**2 + Cz*dw**2)



def calculate_smoothness_gradient(u, v, w, Cx=1e-5, Cy=1e-5, Cz=1e-5,
                                  upper_bc=True):
    """
    Calculates the gradient of the smoothness cost function 
    by taking the Laplacian of the Laplacian of the wind field.
    
    All grids must have the same grid specification.
    
    Parameters
    ----------
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    Cx: float
        Constant controlling smoothness in x-direction
    Cy: float
        Constant controlling smoothness in y-direction
    Cz: float
        Constant controlling smoothness in z-direction
    
    Returns
    -------
    y: float array
        value of gradient of smoothness cost function
    """
    du = np.zeros(w.shape)
    dv = np.zeros(w.shape)
    dw = np.zeros(w.shape)
    grad_u = np.zeros(w.shape)
    grad_v = np.zeros(w.shape)
    grad_w = np.zeros(w.shape)
    scipy.ndimage.filters.laplace(u,du, mode='wrap')
    scipy.ndimage.filters.laplace(v,dv, mode='wrap')
    scipy.ndimage.filters.laplace(w,dw, mode='wrap')
    scipy.ndimage.filters.laplace(du, grad_u, mode='wrap')
    scipy.ndimage.filters.laplace(dv, grad_v, mode='wrap')
    scipy.ndimage.filters.laplace(dw, grad_w, mode='wrap')
           
    # Impermeability condition
    grad_w[0, :, :] = 0
    if(upper_bc == True):
        grad_w[-1, :, :] = 0
    y = np.stack([grad_u*Cx*2, grad_v*Cy*2, grad_w*Cz*2], axis=0)
    return y.flatten()



def calculate_mass_continuity(u, v, w, z, dx, dy, dz, coeff=1500.0, anel=1):
    """
    Calculates the mass continuity cost function.
    
    All grids must have the same grid specification.
    
    Parameters
    ----------
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    z: Float array (1D)
        1D Float array with heights of grid
    coeff: float
        Constant controlling contribution of mass continuity to cost function
    anel: int
        =1 use anelastic approximation, 0=don't
        
    Returns
    -------
    J: float 
        value of mass continuity cost function
    """
    dudx = np.gradient(u, dx, axis=2)
    dvdy = np.gradient(v, dy, axis=1)
    dwdz = np.gradient(w, dz, axis=0)

    if(anel == 1):
        rho = np.exp(-z/10000.0)
        drho_dz = np.gradient(rho, dz, axis=0)
        anel_term = w/rho*drho_dz
    else:
        anel_term = np.zeros(w.shape)
    return coeff*np.sum(np.square(dudx + dvdy + dwdz + anel_term))/2.0



def calculate_mass_continuity_gradient(u, v, w, z, dx,
                                       dy, dz, coeff=1500.0, anel=1,
                                       upper_bc=True):
    """
    Calculates the gradient of mass continuity cost function. 
    
    All grids must have the same grid specification.
    
    Parameters
    ----------
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    z: Float array (1D)
        1D Float array with heights of grid
    coeff: float
        Constant controlling contribution of mass continuity to cost function
    anel: int
        =1 use anelastic approximation, 0=don't
        
    Returns
    -------
    y: float array
        value of gradient of mass continuity cost function
    """
    dudx = np.gradient(u, dx, axis=2)
    dvdy = np.gradient(v, dy, axis=1)
    dwdz = np.gradient(w, dz, axis=0)
    if(anel == 1):
        rho = np.exp(-z/10000.0)
        drho_dz = np.gradient(rho, dz, axis=0)
        anel_term = w/rho*drho_dz
    else:
        anel_term = 0

    div2 = dudx + dvdy + dwdz + anel_term
    
    grad_u = -np.gradient(div2, dx, axis=2)*coeff
    grad_v = -np.gradient(div2, dy, axis=1)*coeff
    grad_w = -np.gradient(div2, dz, axis=0)*coeff
   
    
    # Impermeability condition
    grad_w[0,:,:] = 0
    if(upper_bc == True):
        grad_w[-1,:,:] = 0
    y = np.stack([grad_u, grad_v, grad_w], axis=0)
    return y.flatten()


def calculate_fall_speed(grid, refl_field=None, frz=4500.0):
    """
    Estimates fall speed based on reflectivity.

    Uses methodology of Mike Biggerstaff and Dan Betten
    
    Parameters
    ----------
    Grid: Py-ART Grid
        Py-ART Grid containing reflectivity to calculate fall speed from
    refl_field: str
        String containing name of reflectivity field. None will automatically
        determine the name.
    frz: float
        Height of freezing level in m
        
    Returns
    -------
    3D float array:
        Float array of terminal velocities
    
    """
    # Parse names of velocity field
    if refl_field is None:
        refl_field = pyart.config.get_field_name('reflectivity')
        
    refl = grid.fields[refl_field]['data']
    grid_z = grid.point_z['data']
    term_vel = np.zeros(refl.shape)    
    A = np.zeros(refl.shape)
    B = np.zeros(refl.shape)
    rho = np.exp(-grid_z/10000.0)
    A[np.logical_and(grid_z < frz, refl < 55)] = -2.6
    B[np.logical_and(grid_z < frz, refl < 55)] = 0.0107
    A[np.logical_and(grid_z < frz, 
                     np.logical_and(refl >= 55, refl < 60))] = -2.5
    B[np.logical_and(grid_z < frz, 
                     np.logical_and(refl >= 55, refl < 60))] = 0.013
    A[np.logical_and(grid_z < frz, refl > 60)] = -3.95
    B[np.logical_and(grid_z < frz, refl > 60)] = 0.0148
    A[np.logical_and(grid_z >= frz, refl < 33)] = -0.817
    B[np.logical_and(grid_z >= frz, refl < 33)] = 0.0063
    A[np.logical_and(grid_z >= frz,
                     np.logical_and(refl >= 33, refl < 49))] = -2.5
    B[np.logical_and(grid_z >= frz,
                     np.logical_and(refl >= 33, refl < 49))] = 0.013
    A[np.logical_and(grid_z >= frz, refl > 49)] = -3.95
    B[np.logical_and(grid_z >= frz, refl > 49)] = 0.0148

    fallspeed = A*np.power(10, refl*B)*np.power(1.2/rho, 0.4)
    del A, B, rho
    return fallspeed



def calculate_background_cost(u, v, w, weights, u_back, v_back, Cb=0.01):
    """
    Calculates the background cost function.
    
    Parameters
    ----------
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    weights: Float array 
        Weights for each point to consider into cost function
    u_back: 1D float array
        Zonal winds vs height from sounding
    w_back: 1D float array
        Meridional winds vs height from sounding    
    Cb: float
        Weight of background constraint to total cost function
        
    Returns
    -------
    cost: float 
        value of background cost function
    """
    the_shape = u.shape
    cost = 0
    for i in range(the_shape[0]):
        cost += (Cb*np.sum(np.square(u[i]-u_back[i])*(weights[i]) +
                           np.square(v[i]-v_back[i])*(weights[i])))
    return cost



def calculate_background_gradient(u, v, w, weights, u_back, v_back, Cb=0.01):
    """
    Calculates the gradient of the background cost function.
    
    Parameters
    ----------
    u: Float array
        Float array with u component of wind field
    v: Float array
        Float array with v component of wind field
    w: Float array
        Float array with w component of wind field
    weights: Float array 
        Weights for each point to consider into cost function
    u_back: 1D float array
        Zonal winds vs height from sounding
    w_back: 1D float array
        Meridional winds vs height from sounding    
    Cb: float
        Weight of background constraint to total cost function
        
    Returns
    -------
    y: float array
        value of gradient of background cost function
    """
    the_shape = u.shape
    u_grad = np.zeros(the_shape)
    v_grad = np.zeros(the_shape)
    w_grad = np.zeros(the_shape)

    for i in range(the_shape[0]):
        u_grad[i] = Cb*2*(u[i]-u_back[i])*(weights[i])
        v_grad[i] = Cb*2*(v[i]-v_back[i])*(weights[i])

    y = np.stack([u_grad, v_grad, w_grad], axis=0)
    return y.flatten()


def calculate_vertical_vorticity_cost(u, v, w, dx, dy, dz, Ut, Vt, 
                                      coeff=1e-5):
    """
    Calculates the cost function due to deviance from vertical vorticity
    equation.
    
    Parameters
    ----------
    u: 3D array
        Float array with u component of wind field
    v: 3D array
        Float array with v component of wind field
    w: 3D array
        Float array with w component of wind field
    dx: float array
        Spacing in x grid
    dy: float array
        Spacing in y grid
    dz: float array
        Spacing in z grid
    coeff: float
        Weighting coefficient
    Ut: float
        U component of storm motion
    Vt: float
        V component of storm motion
        
    Returns
    -------
    Jv: float
        Value of vertical vorticity cost function.
    """
    dvdz = np.gradient(v, dz, axis=0)
    dudz = np.gradient(u, dz, axis=0)
    dwdz = np.gradient(w, dx, axis=2)
    dvdx = np.gradient(v, dx, axis=2)
    dwdy = np.gradient(w, dy, axis=1)
    dwdx = np.gradient(w, dx, axis=2)
    dudx = np.gradient(u, dx, axis=2)
    dvdy = np.gradient(v, dy, axis=2)
    dudy = np.gradient(u, dy, axis=1)
    zeta = dvdx - dudy
    dzeta_dx = np.gradient(zeta, dx, axis=2)
    dzeta_dy = np.gradient(zeta, dy, axis=1)
    dzeta_dz = np.gradient(zeta, dz, axis=0)
    jv_array = (u- Ut)*dzeta_dx + (v - Vt)*dzeta_dy + w*dzeta_dz + (dvdz*dwdx -
               dudz*dwdy) + zeta*(dudx + dvdy)
    return np.sum(coeff*jv_array**2)
    

def calculate_vertical_vorticity_gradient(u, v, w, dx, dy, dz, Ut, Vt, 
                                          coeff=1e-5):
    """
    Calculates the gradient of the cost function due to deviance from vertical 
    vorticity equation.
    
    Parameters
    ----------
    u: 3D array
        Float array with u component of wind field
    v: 3D array
        Float array with v component of wind field
    w: 3D array
        Float array with w component of wind field
    dx: float array
        Spacing in x grid
    dy: float array
        Spacing in y grid
    dz: float array
        Spacing in z grid
    Ut: float
        U component of storm motion
    Vt: float
        V component of storm motion
    coeff: float
        Weighting coefficient        
    Returns
    -------
    Jv: 1D float array
        Value of the gradient of the vertical vorticity cost function.
    """
    
    # First we will calculate dzeta_dt
    
    # First derivatives
    dvdz = np.gradient(v, dz, axis=0)
    dudz = np.gradient(u, dz, axis=0)
    dwdy = np.gradient(w, dy, axis=1)
    dudx = np.gradient(u, dx, axis=2)
    dvdy = np.gradient(v, dy, axis=2)
    dwdx = np.gradient(w, dx, axis=2)
    dvdx = np.gradient(v, dx, axis=2)
    dwdx = np.gradient(w, dx, axis=2)
    dudz = np.gradient(u, dz, axis=0)
    dudy = np.gradient(u, dy, axis=1)
    
    zeta = dvdx - dudy
    dzeta_dx = np.gradient(zeta, dx, axis=2)
    dzeta_dy = np.gradient(zeta, dy, axis=1)
    dzeta_dz = np.gradient(zeta, dz, axis=0)
    
    # Second deriviatives
    dwdydz = np.gradient(dwdy, dz, axis=0)
    dwdxdz = np.gradient(dwdx, dz, axis=0)
    dudzdy = np.gradient(dudz, dy, axis=1)
    dvdxdy = np.gradient(dvdx, dy, axis=1)
    dudx2 = np.gradient(dudx, dx, axis=2)
    dudxdy = np.gradient(dudx, dy, axis=1)
    dudxdz = np.gradient(dudx, dz, axis=0)
    dudy2 = np.gradient(dudx, dy, axis=1)
    
    
    dzeta_dt = ((u - Ut)*dzeta_dx + (v - Vt)*dzeta_dy + w*dzeta_dz + 
        (dvdz*dwdx - dudz*dwdy) + zeta*(dudx + dvdy))
    
    # Now we intialize our gradient value
    u_grad = np.zeros(u.shape)
    v_grad = np.zeros(v.shape)
    w_grad = np.zeros(w.shape)
    

    # Vorticity Advection
    u_grad += dzeta_dx + (Ut - u)*dudxdy + (Vt - v)*dudxdy
    v_grad += dzeta_dy + (Vt - v)*dvdxdy + (Ut - u)*dvdxdy
    w_grad += dzeta_dz
    
    # Tilting term
    u_grad += dwdydz
    v_grad += dwdxdz
    w_grad += dudzdy - dudxdz
    
    # Stretching term
    u_grad += -dudxdy + dudy2 - dzeta_dx
    u_grad += -dudx2 + dudxdy - dzeta_dy
    
    # Multiply by 2*dzeta_dt according to chain rule
    u_grad = u_grad*2*dzeta_dt*coeff
    v_grad = v_grad*2*dzeta_dt*coeff
    w_grad = w_grad*2*dzeta_dt*coeff
    
    y = np.stack([u_grad, v_grad, w_grad], axis=0)
    return y.flatten()
