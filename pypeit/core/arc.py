import inspect

import numpy as np
from matplotlib import gridspec
from matplotlib import pyplot as plt


import scipy
from astropy import stats

from pypeit import debugger

from pypeit import msgs
from pypeit import utils
#from pypeit.core.wavecal import autoid
from pypeit.core.wavecal import wvutils
from pypeit.core.wavecal import wv_fitting
from pypeit.core import fitting
from IPython import embed


from pypeit.core import pydl
from pypeit.core import qa


def fit2darc(all_wv,all_pix,all_orders,nspec, nspec_coeff=4,norder_coeff=4,sigrej=3.0, func2d='legendre2d', debug=False):
    """Routine to obtain the 2D wavelength solution for an echelle spectrograph. This is calculated from the spec direction
    pixelcentroid and the order number of identified arc lines. The fit is a simple least-squares with rejections.
    This is a port of the XIDL code: x_fit2darc.pro

    Parameters
    ----------
    all_wv: np.array
     wavelength of the identified lines
    all_pix: np.array
      y-centroid position of the identified lines
    all_orders: np.array
      order number of the identified lines
    nspec: int
      Size of the image in the spectral direction
    nspec_coeff : np.int
      order of the fitting along the spectral (pixel) direction for each order
    norder_coeff : np.int
      order of the fitting in the order direction
    sigrej: np.float
      sigma level for the rejection
    debug: boolean
      Extra plots to check the status of the procedure

    Returns:
    -------
    """

    # Normalize  for pixels. Fits are performed in normalized units (pixels/(nspec-1) to be able to deal with various
    # binnings.
    min_spec = 0.0
    max_spec = 1.0
    xnspecmin1 = float(nspec-1)
    # Normalize for orders
    min_order = np.min(all_orders)
    max_order = np.max(all_orders)

    if debug:
        # set some plotting parameters
        utils.pyplot_rcparams()
        plt.figure(figsize=(7,5))
        msgs.info("Plot identified lines")
        cm = plt.cm.get_cmap('RdYlBu_r')
        sc = plt.scatter(all_orders, all_pix,c=all_wv/10000., cmap=cm)
        cbar = plt.colorbar(sc)
        cbar.set_label(r'Wavelength [$\mu$m]', rotation=270,
                       labelpad=20)
        plt.xlabel(r'Normalized Orders')
        plt.ylabel(r'Normalized Pixels')
        plt.title(r'Location of the identified lines')
        plt.show()


    # Fit the product of wavelength and order number with a 2d legendre polynomial
    all_wv_order = all_wv * all_orders
    fitmask, coeff2 = fitting.robust_polyfit_djs(all_pix/xnspecmin1, all_wv_order, (nspec_coeff, norder_coeff),x2=all_orders,
                                               function=func2d, maxiter=100, lower=sigrej, upper=sigrej,
                                               minx=min_spec,maxx=max_spec, minx2=min_order, maxx2=max_order,
                                               use_mad=True, sticky=False)
    wv_order_mod = fitting.func_val(coeff2, all_pix/xnspecmin1, func2d, x2=all_orders,
                                               minx=min_spec, maxx=max_spec, minx2=min_order, maxx2=max_order)
    resid = (wv_order_mod[fitmask]-all_wv_order[fitmask])
    fin_rms = np.std(resid)
    msgs.info("RMS: {0:.5f} Ang*Order#".format(fin_rms))

    orders = np.unique(all_orders)
    fit_dict = dict(coeffs=coeff2, orders=orders,
                    nspec_coeff=nspec_coeff, norder_coeff=norder_coeff,
                    min_spec=min_spec, max_spec=max_spec,
                    min_order=min_order, max_order=max_order,
                    nspec=nspec, all_pix=all_pix, all_wv=all_wv,
                    func2d=func2d,xnorm=xnspecmin1,
                    all_orders=all_orders, all_mask=fitmask)


    if debug:
        fit2darc_global_qa(fit_dict)
        fit2darc_orders_qa(fit_dict)

    return fit_dict



def fit2darc_global_qa(fit_dict, outfile=None):
    """ QA on 2D fit of the wavelength solution.

    Parameters
    ----------
    fit_dict: dict
      dict of the 2D arc solution
    outfile:
      parameter for QA

    Returns
    -------
    """

    msgs.info("Creating QA for 2D wavelength solution")

    utils.pyplot_rcparams()

    # Extract info from fit_dict
    nspec = fit_dict['nspec']
    orders = fit_dict['orders']
    nspec_coeff = fit_dict['nspec_coeff']
    norder_coeff = fit_dict['norder_coeff']
    all_wv = fit_dict['all_wv']
    all_pix = fit_dict['all_pix']
    all_orders = fit_dict['all_orders']
    fitmask = fit_dict['all_mask']
    coeffs = fit_dict['coeffs']
    func2d = fit_dict['func2d']
    min_spec = fit_dict['min_spec']
    max_spec = fit_dict['max_spec']
    min_order = fit_dict['min_order']
    max_order = fit_dict['max_order']
    xnorm = fit_dict['xnorm']
    resid_wl_global = []

    # Define pixels array
    spec_vec_norm = np.arange(nspec)/xnorm

    # Define figure properties
    plt.figure(figsize=(8, 5))

    # Variable where to store the max wavelength covered by the
    # spectrum
    mx = 0.

    # Loop over orders
    for ii in orders:

        # define the color
        rr = (ii - np.max(orders)) / (np.min(orders) - np.max(orders))
        gg = 0.0
        bb = (ii - np.min(orders)) / (np.max(orders) - np.min(orders))

        # evaluate solution
        wv_order_mod = utils.func_val(coeffs, spec_vec_norm, func2d, x2=np.ones_like(spec_vec_norm)*ii,
                                               minx=min_spec, maxx=max_spec, minx2=min_order, maxx2=max_order)
        # Plot solution
        plt.plot(wv_order_mod / ii, spec_vec_norm*xnorm, color=(rr, gg, bb),
                 linestyle='-', linewidth=2.5)

        # Evaluate residuals at each order
        on_order = all_orders == ii
        this_pix = all_pix[on_order]
        this_wv = all_wv[on_order]
        this_msk = fitmask[on_order]
        this_order = all_orders[on_order]
        wv_order_mod_resid = utils.func_val(coeffs, this_pix/xnorm, func2d, x2=this_order,
                                               minx=min_spec, maxx=max_spec, minx2=min_order, maxx2=max_order)
        resid_wl = (wv_order_mod_resid / ii - this_wv)
        resid_wl_global = np.append(resid_wl_global, resid_wl[this_msk])
        plt.scatter((wv_order_mod_resid[~this_msk] / ii) + \
                    100. * resid_wl[~this_msk], this_pix[~this_msk], \
                    marker='x', color='black', linewidths=2.5, s=16.)
        plt.scatter((wv_order_mod_resid[this_msk] / ii) + \
                    100. * resid_wl[this_msk], this_pix[this_msk], \
                    color=(rr, gg, bb), linewidth=2.5, s=16.)
        if np.max(wv_order_mod_resid / ii) > mx:
            mx = np.max(wv_order_mod_resid / ii)

    rms_global = np.std(resid_wl_global)

    plt.text(mx, np.max(spec_vec_norm*xnorm), r'residuals $\times$100', \
             ha="right", va="top")
    plt.title(r'Arc 2D FIT, norder_coeff={:d}, nspec_coeff={:d}, RMS={:5.3f} Ang*Order#'.format(
        norder_coeff, nspec_coeff, rms_global))
    plt.xlabel(r'Wavelength [$\AA$]')
    plt.ylabel(r'Row [pixel]')

    # Finish
    if outfile is not None:
        plt.savefig(outfile, dpi=800)
        plt.close()
    else:
        plt.show()

    # restore default rcparams
    utils.pyplot_rcparams_default()


def fit2darc_orders_qa(fit_dict, outfile=None):
    """ QA on 2D fit of the wavelength solution of an Echelle spectrograph.
    Each panel contains a single order with the global fit and the
    residuals.

    Parameters
    ----------
    fit_dict: dict
      dict of the 2D arc solution
    outfile:
      parameter for QA

    Returns
    -------
    """

    msgs.info("Creating QA for 2D wavelength solution")

    utils.pyplot_rcparams()

    # Extract info from fit_dict
    # Extract info from fit_dict
    nspec = fit_dict['nspec']
    orders = fit_dict['orders']
    nspec_coeff = fit_dict['nspec_coeff']
    norder_coeff = fit_dict['norder_coeff']
    all_wv = fit_dict['all_wv']
    all_pix = fit_dict['all_pix']
    all_orders = fit_dict['all_orders']
    fitmask = fit_dict['all_mask']
    coeffs = fit_dict['coeffs']
    func2d = fit_dict['func2d']
    min_spec = fit_dict['min_spec']
    max_spec = fit_dict['max_spec']
    min_order = fit_dict['min_order']
    max_order = fit_dict['max_order']
    xnorm = fit_dict['xnorm']
    resid_wl_global = []

    # Define pixels array
    spec_vec_norm = np.arange(nspec)/xnorm

    # set the size of the plot
    nrow = np.int(2)
    ncol = np.int(np.ceil(len(orders) / 2.))
    fig = plt.figure(figsize=(5 * ncol, 6 * nrow))

    outer = gridspec.GridSpec(nrow, ncol, wspace=0.3, hspace=0.2)

    for ii_row in range(nrow):
        for ii_col in range(ncol):
            if (ii_row * ncol + ii_col) < len(orders):
                inner = gridspec.GridSpecFromSubplotSpec(2, 1,
                                                         height_ratios=[2, 1], width_ratios=[1],
                                                         subplot_spec=outer[ii_row * ncol + ii_col],
                                                         wspace=0.1, hspace=0.0)
                ax0 = plt.Subplot(fig, inner[0])
                ax1 = plt.Subplot(fig, inner[1], sharex=ax0)
                plt.setp(ax0.get_xticklabels(), visible=False)

                ii = orders[ii_row * ncol + ii_col]

                # define the color
                rr = (ii - np.max(orders)) / (np.min(orders) - np.max(orders))
                gg = 0.0
                bb = (ii - np.min(orders)) / (np.max(orders) - np.min(orders))

                # Evaluate function
                # evaluate solution
                wv_order_mod = utils.func_val(coeffs, spec_vec_norm, func2d, x2=ii*np.ones_like(spec_vec_norm),
                                              minx=min_spec, maxx=max_spec, minx2=min_order, maxx2=max_order)
                # Evaluate delta lambda
                dwl = (wv_order_mod[-1] - wv_order_mod[0])/ii/xnorm/(spec_vec_norm[-1] - spec_vec_norm[0])

                # Estimate the residuals
                on_order = all_orders == ii
                this_order = all_orders[on_order]
                this_pix = all_pix[on_order]
                this_wv = all_wv[on_order]
                this_msk = fitmask[on_order]

                wv_order_mod_resid = utils.func_val(coeffs, this_pix/xnorm, func2d, x2=this_order,
                                              minx=min_spec, maxx=max_spec, minx2=min_order, maxx2=max_order)
                resid_wl = (wv_order_mod_resid/ii - this_wv)
                resid_wl_global = np.append(resid_wl_global, resid_wl[this_msk])

                # Plot the fit
                ax0.set_title('Order = {0:0.0f}'.format(ii))
                ax0.plot(spec_vec_norm*xnorm, wv_order_mod / ii / 10000., color=(rr, gg, bb), linestyle='-',
                         linewidth=2.5)
                ax0.scatter(this_pix[~this_msk], (wv_order_mod_resid[~this_msk] / ii / 10000.) + \
                            100. * resid_wl[~this_msk] / 10000., marker='x', color='black', \
                            linewidth=2.5, s=16.)
                ax0.scatter(this_pix[this_msk], (wv_order_mod_resid[this_msk] / ii / 10000.) + \
                            100. * resid_wl[this_msk] / 10000., color=(rr, gg, bb), \
                            linewidth=2.5, s=16.)

                ax0.set_ylabel(r'Wavelength [$\mu$m]')

                # Plot the residuals
                ax1.scatter(this_pix[~this_msk], (resid_wl[~this_msk] / dwl), marker='x', color='black', \
                            linewidth=2.5, s=16.)
                ax1.scatter(this_pix[this_msk], (resid_wl[this_msk] / dwl), color=(rr, gg, bb), \
                            linewidth=2.5, s=16.)
                ax1.axhline(y=0., color=(rr, gg, bb), linestyle=':', linewidth=2.5)
                ax1.get_yaxis().set_label_coords(-0.15, 0.5)

                rms_order = np.std(resid_wl[this_msk])

                ax1.set_ylabel(r'Res. [pix]')

                ax0.text(0.1, 0.9, r'RMS={0:.3f} Pixel'.format(rms_order / np.abs(dwl)), ha="left", va="top",
                         transform=ax0.transAxes)
                ax0.text(0.1, 0.8, r'$\Delta\lambda$={0:.3f} Pixel/$\AA$'.format(np.abs(dwl)), ha="left", va="top",
                         transform=ax0.transAxes)
                ax0.get_yaxis().set_label_coords(-0.15, 0.5)

                fig.add_subplot(ax0)
                fig.add_subplot(ax1)

    rms_global = np.std(resid_wl_global)

    fig.text(0.5, 0.04, r'Row [pixel]', ha='center', size='large')
    fig.suptitle(
        r'Arc 2D FIT, norder_coeff={:d}, nspec_coeff={:d}, RMS={:5.3f} Ang*Order#, residuals $\times$100'.format(
            norder_coeff,
            nspec_coeff, rms_global))

    # Finish
    if outfile is not None:
        plt.savefig(outfile, dpi=800)
        plt.close()
    else:
        plt.show()


# JFH CAn we replace reasize with this simpler function:  rebin_factor
# https://scipy-cookbook.readthedocs.io/items/Rebinning.html
def resize_mask2arc(shape_arc, slitmask_orig):
    """
    Resizes a slitmask created with some original binning to be a slitmak relevant to an arc with a different binning

    Args:
        shape_arc: tuple
            shape of the arc
        slitmask_orig: ndarray, float
            original slitmask
    Returns:
        slitmask: ndarray, float
            Slitmask with shape corresponding to that of the arc

    """
    (nspec, nspat) = shape_arc
    # Is our arc a different size than the other calibs? If yes, slit_left/slit_righ, slitpix, and inmask will
    # be a different size
    (nspec_orig,nspat_orig) = slitmask_orig.shape
    if nspec_orig != nspec:
        if ((nspec_orig > nspec) & (nspec_orig % nspec != 0)) | ((nspec > nspec_orig) & (nspec % nspec_orig != 0)):
            msgs.error('Problem with images sizes. arcimg size and calibration size need to be integer multiples of each other')
        else:
            msgs.info('Calibration images have different binning than the arcimg. Resizing calibs for arc spectrum extraction.')
        slitmask = utils.rebin(slitmask_orig, (nspec, nspat))
        # Previous line using skimage
        #slitmask = ((np.round(resize(slitmask_orig.astype(np.integer), (nspec, nspat), preserve_range=True, order=0))).astype(np.integer)).astype(slitmask_orig.dtype)
    else:
        slitmask = slitmask_orig

    return slitmask

def resize_slits2arc(shape_arc, shape_orig, trace_orig):
    """
    Resizes a a trace created with some original binning to be a relevant to an arc with a different binning

    Args:
        shape_arc: tuple
            shape of the arc
        shape_orig: tuple
            original shape of the images used to create the trace
        trace_orig: ndarray, float
            trace that you want to resize
    Returns:
        `numpy.ndarray`: trace corresponding to the binning of the arc

    """
    (nspec, nspat) = shape_arc
    # Is our arc a different size than the other calibs? If yes, slit_left/slit_righ, slitpix, and inmask will
    # be a different size
    (nspec_orig,nspat_orig) = shape_orig
    if nspec_orig != nspec:
        msgs.info('Calibration images have different binning than the arcimg. Resizing calibs for arc spectrum extraction.')
        spec_vec_orig = np.arange(nspec_orig)/float(nspec_orig - 1)
        spec_vec = np.arange(nspec)/float(nspec - 1)
        spat_ratio = float(nspat)/float(nspat_orig)
        trace = (scipy.interpolate.interp1d(spec_vec_orig, spat_ratio*trace_orig, axis=0, bounds_error=False,fill_value='extrapolate'))(spec_vec)
    else:
        trace = trace_orig

    return trace


def resize_spec(spec_from, nspec_to):
    """

    Args:
        spec_from: ndarray, float (nspec, nslits) or (nspec,)
          Input spectrum which you want to resize via interpolation
        nspec_to: int, size of spectrum you to resize to

    Returns:
        spec_to: ndarray, float, same size as spec_from
          New spectra or spectrum with size nspec_to

    """

    nspec_from = spec_from.shape[0]
    # Is our arc a different size than the other calibs? If yes, slit_left/slit_righ, slitpix, and inmask will
    # be a different size
    if nspec_from != nspec_to:
        spec_vec_from = np.arange(nspec_from)/float(nspec_from - 1)
        spec_vec_to = np.arange(nspec_to)/float(nspec_to - 1)
        spec_to = (scipy.interpolate.interp1d(spec_vec_from, spec_from, axis=0, bounds_error=False,fill_value='extrapolate'))(spec_vec_to)
    else:
        spec_to = spec_from

    return spec_to


def get_censpec(slit_cen, slitmask, arcimg, gpm=None, box_rad=3.0, nonlinear_counts=1e10,
                slit_bpm=None):
    """
    Extract a boxcar spectrum down the center of the slit

    Args:

        slit_cen (`numpy.ndarray`):
            Trace down the center of the slit
        slitmask (`numpy.ndarray`):
            Image where pixel values identify its parent slit,
            starting with 0. Pixels with -1 are not part of any slit.
            Shape must match `arcimg`.
        arcimg (`numpy.ndarray`):
            Image to extract the arc from. This should be an arcimage
            or perhaps a frame with night sky lines.
        gpm (`numpy.ndarray`, optional):
            Input mask image with same shape as arcimg. Convention
            True = good and False = bad. If None, all pixels are
            considered good.
        box_rad (:obj:`float`, optional):
            Half-width of the boxcar (floating-point pixels) in the
            spatial direction used to extract the arc.
        nonlinear_counts (:obj:`float`, optional):
            Values exceeding this input value are masked as bad.

    Returns:
        Returns three numpy.ndarray objects:
            - Array containing the extracted arc spectrum for each
              slit. Shape is (nspec, nslits)
            - Bad-pixel mask for the spectra. Shape is (nspec,
              nslits).
            - Bad-slit mask, True means the entire spectrum is bad.
              Shape is (nslits,).
    """
    # Initialize the good pixel mask
    _gpm = slitmask > -1 if gpm is None else gpm & (slitmask > -1)
    # Mask saturated parts of the arc image for the extraction
    _gpm = _gpm & (arcimg < nonlinear_counts)

    # Inialize output
    arc_spec = np.zeros_like(slit_cen)

    # Iterate over slits
    nslits = slit_cen.shape[1]
    nspat = arcimg.shape[1]
    spat = np.arange(nspat)
    for islit in range(nslits):
        if slit_bpm is not None and slit_bpm[islit]:
            msgs.info('Ignoring masked slit {}'.format(islit))
            # TODO -- Avoid using NaNs
            arc_spec[:,islit] = np.nan
            continue
        msgs.info('Extracting approximate arc spectrum along the center of slit {0}'.format(islit))
        # Create a mask for the pixels that will contribue to the arc
        arcmask = _gpm & (np.absolute(spat[None,:] - slit_cen[:,islit,None]) < box_rad)
        # Trimming the image makes this much faster
        indx = np.nonzero(np.any(arcmask, axis=0))[0]
        if len(indx) == 0:  # Must have been a masked slit
            arc_spec[:,islit] = np.nan
            continue
        left, right = np.clip([indx[0]-4, indx[-1]+5], 0, nspat)
        # TODO JFH Add cenfunc and std_func here, using median and the use_mad fix.
        arc_spec[:,islit] = stats.sigma_clipped_stats(arcimg[:,left:right],
                                                      mask=np.invert(arcmask[:,left:right]),
                                                      sigma=3.0, axis=1)[1]

    # Get the mask, set the masked values to 0, and return
    arc_spec_bpm = np.isnan(arc_spec)
    arc_spec[arc_spec_bpm] = 0.0
    return arc_spec, arc_spec_bpm, np.all(arc_spec_bpm, axis=0)

def detect_peaks(x, mph=None, mpd=1, threshold=0, edge='rising',
                 kpsh=False, valley=False, show=False, ax=None):
    """Detect peaks in data based on their amplitude and other features.

    Parameters
    ----------
    x : 1D array_like
        data.
    mph : {None, number}, optional (default = None)
        detect peaks that are greater than minimum peak height (if parameter
        `valley` is False) or peaks that are smaller than maximum peak height
        (if parameter `valley` is True).
    mpd : positive integer, optional (default = 1)
        detect peaks that are at least separated by minimum peak distance (in
        number of data).
    threshold : positive number, optional (default = 0)
        detect peaks (valleys) that are greater (smaller) than `threshold`
        in relation to their immediate neighbors.
    edge : {None, 'rising', 'falling', 'both'}, optional (default = 'rising')
        for a flat peak, keep only the rising edge ('rising'), only the
        falling edge ('falling'), both edges ('both'), or don't detect a
        flat peak (None).
    kpsh : bool, optional (default = False)
        keep peaks with same height even if they are closer than `mpd`.
    valley : bool, optional (default = False)
        if True (1), detect valleys (local minima) instead of peaks.
    show : bool, optional (default = False)
        if True (1), plot data in matplotlib figure.
    ax : a matplotlib.axes.Axes instance, optional (default = None).

    Returns
    -------
    ind : 1D array_like
        indeces of the peaks in `x`.

    Notes
    -----
    The detection of valleys instead of peaks is performed internally by simply
    negating the data::
        
        ind_valleys = detect_peaks(-x)

    The function can handle NaN's

    See this IPython Notebook [1]_.

    .. code-block:: python

        __author__ = "Marcos Duarte, https://github.com/demotu/BMC"
        __version__ = "1.0.5"
        __license__ = "MIT"

    Version history:

        * '1.0.5': The sign of `mph` is inverted if parameter `valley` is True

    References
    ----------
    .. [1] http://nbviewer.ipython.org/github/demotu/BMC/blob/master/notebooks/DetectPeaks.ipynb

    Examples
    --------
    >>> from detect_peaks import detect_peaks
    >>> x = np.random.randn(100)
    >>> x[60:81] = np.nan
    >>> # detect all peaks and plot data
    >>> ind = detect_peaks(x, show=True)
    >>> print(ind)

    >>> x = np.sin(2*np.pi*5*np.linspace(0, 1, 200)) + np.random.randn(200)/5
    >>> # set minimum peak height = 0 and minimum peak distance = 20
    >>> detect_peaks(x, mph=0, mpd=20, show=True)

    >>> x = [0, 1, 0, 2, 0, 3, 0, 2, 0, 1, 0]
    >>> # set minimum peak distance = 2
    >>> detect_peaks(x, mpd=2, show=True)

    >>> x = np.sin(2*np.pi*5*np.linspace(0, 1, 200)) + np.random.randn(200)/5
    >>> # detection of valleys instead of peaks
    >>> detect_peaks(x, mph=-1.2, mpd=20, valley=True, show=True)

    >>> x = [0, 1, 1, 0, 1, 1, 0]
    >>> # detect both edges
    >>> detect_peaks(x, edge='both', show=True)

    >>> x = [-2, 1, -2, 2, 1, 1, 3, 0]
    >>> # set threshold = 2
    >>> detect_peaks(x, threshold = 2, show=True)

    """

    x = np.atleast_1d(x).astype('float64')
    if x.size < 3:
        return np.array([], dtype=int)
    if valley:
        x = -x
        if mph is not None:
            mph = -mph
    # find indices of all peaks
    dx = x[1:] - x[:-1]
    # handle NaN's
    indnan = np.where(np.isnan(x))[0]
    if indnan.size:
        x[indnan] = np.inf
        dx[np.where(np.isnan(dx))[0]] = np.inf
    ine, ire, ife = np.array([[], [], []], dtype=int)
    if not edge:
        ine = np.where((np.hstack((dx, 0)) < 0) & (np.hstack((0, dx)) > 0))[0]
    else:
        if edge.lower() in ['rising', 'both']:
            ire = np.where((np.hstack((dx, 0)) <= 0) & (np.hstack((0, dx)) > 0))[0]
        if edge.lower() in ['falling', 'both']:
            ife = np.where((np.hstack((dx, 0)) < 0) & (np.hstack((0, dx)) >= 0))[0]
    ind = np.unique(np.hstack((ine, ire, ife)))
    # handle NaN's
    if ind.size and indnan.size:
        # NaN's and values close to NaN's cannot be peaks
        ind = ind[np.in1d(ind, np.unique(np.hstack((indnan, indnan - 1, indnan + 1))), invert=True)]
    # first and last values of x cannot be peaks
    if ind.size and ind[0] == 0:
        ind = ind[1:]
    if ind.size and ind[-1] == x.size - 1:
        ind = ind[:-1]
    # remove peaks < minimum peak height
    if ind.size and mph is not None:
        ind = ind[x[ind] >= mph]
    # remove peaks - neighbors < threshold
    if ind.size and threshold > 0:
        dx = np.min(np.vstack([x[ind] - x[ind - 1], x[ind] - x[ind + 1]]), axis=0)
        ind = np.delete(ind, np.where(dx < threshold)[0])
    # detect small peaks closer than minimum peak distance
    if ind.size and mpd > 1:
        ind = ind[np.argsort(x[ind])][::-1]  # sort ind by peak height
        idel = np.zeros(ind.size, dtype=bool)
        for i in range(ind.size):
            if not idel[i]:
                # keep peaks with the same height if kpsh is True
                idel = idel | (ind >= ind[i] - mpd) & (ind <= ind[i] + mpd) \
                       & (x[ind[i]] > x[ind] if kpsh else True)
                idel[i] = 0  # Keep current peak
        # remove the small peaks and sort back the indices by their occurrence
        ind = np.sort(ind[~idel])

    if show:
        if indnan.size:
            x[indnan] = np.nan
        if valley:
            x = -x
            if mph is not None:
                mph = -mph
        _plot(x, mph, mpd, threshold, edge, valley, ax, ind)

    return ind


def _plot(x, mph, mpd, threshold, edge, valley, ax, ind):
    """Plot results of the detect_peaks function, see its help."""


    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(8, 4))

    ax.plot(x, 'b', lw=1)
    if ind.size:
        label = 'valley' if valley else 'peak'
        label = label + 's' if ind.size > 1 else label
        ax.plot(ind, x[ind], '+', mfc=None, mec='r', mew=2, ms=8,
                label='%d %s' % (ind.size, label))
        ax.legend(loc='best', framealpha=.5, numpoints=1)
    ax.set_xlim(-.02 * x.size, x.size * 1.02 - 1)
    ymin, ymax = x[np.isfinite(x)].min(), x[np.isfinite(x)].max()
    yrange = ymax - ymin if ymax > ymin else 1
    ax.set_ylim(ymin - 0.1 * yrange, ymax + 0.1 * yrange)
    ax.set_xlabel('Data #', fontsize=14)
    ax.set_ylabel('Amplitude', fontsize=14)
    mode = 'Valley detection' if valley else 'Peak detection'
    ax.set_title("%s (mph=%s, mpd=%f, threshold=%s, edge='%s')"
                 % (mode, str(mph), mpd, str(threshold), edge))
    # plt.grid()
    plt.show()

def iter_continuum(spec, inmask=None, fwhm=4.0, sigthresh = 2.0, sigrej=3.0, niter_cont = 3, cont_samp = 30, cont_frac_fwhm=1.0,
                   cont_mask_neg=False, qa_title='', npoly=None, debug_peak_find=False, debug=False):
    """
    Routine to determine the continuum and continuum pixels in spectra with peaks.

    Args:
       spec (ndarray, float,  shape (nspec,)  A 1D spectrum for which the continuum is to be characterized
       inmask: ndarray, bool, shape (nspec,)   A mask indicating which pixels are good. True = Good, False=Bad
       niter_cont: int, default = 3
            Number of iterations of peak finding, masking, and continuum fitting used to define the continuum.
       npoly: int, default = None
            If set the code will perform a polynomimal fit to the interpolate a running median filter of the
            continuum points instead of the default behavior which is to just return the
            interpolated running median filter
       sigthresh: float, default = 2.0
            Signifiance threshold for peak finding
       sigrej: float, default = 3.0
            Sigma clipping rejection threshold for threshold determination
       fwhm:  float, default = 4.0
            Number of pixels per fwhm resolution element.
       cont_samp: float, default = 30.0
            The number of samples across the spectrum used for continuum subtraction. Continuum subtraction is done via
            median filtering, with a width of ngood/cont_samp, where ngood is the number of good pixels for estimating the continuum
            (i.e. that don't have peaks).
       cont_frac_fwhm float, default = 1.0
            Width used for masking peaks in the spectrum when the continuum is being defined. Expressed as a fraction of the fwhm
            parameter
       cont_mask_neg: bool, default = False
           If True, the code will also search for negative peaks when iteratively determining the continuum. This option is
           used for object finding in the near-IR where there will also be negative peaks.
       cont_samp: float, default = 30.0
           The number of samples across the spectrum used for continuum subtraction. Continuum subtraction is done via
           median filtering, with a width of ngood/cont_samp, where ngood is the number of good pixels for estimating the continuum
        debug: bool, default = False
           Show plots for debugging

    Returns: (cont, cont_mask)
        cont: ndarray, float, shape (nspec) The continuum determined
        cont_mask: ndarray, bool, shape (nspec) A mask indicating which pixels were used for continuum determination


    """

    if inmask is None:
        inmask = np.ones(spec.size,dtype=bool)
        cont_mask = np.copy(inmask)
    else:
        cont_mask = np.copy(inmask)

    nspec = spec.size
    spec_vec = np.arange(nspec)
    cont_now = np.zeros(nspec)
    mask_sm = np.round(cont_frac_fwhm*fwhm).astype(int)
    mask_odd = mask_sm + 1 if mask_sm % 2 == 0 else mask_sm
    for iter in range(niter_cont):
        spec_sub = spec - cont_now
        mask_sigclip = np.invert(cont_mask & inmask)
        (mean, med, stddev) = stats.sigma_clipped_stats(spec_sub, mask=mask_sigclip, sigma_lower=sigrej,
                                                        sigma_upper=sigrej, cenfunc='median', stdfunc=utils.nan_mad_std)
        # be very liberal in determining threshold for continuum determination
        thresh = med + sigthresh*stddev
        pixt_now = detect_peaks(spec_sub, mph=thresh, mpd=fwhm*0.75, show=debug_peak_find)
        # mask out the peaks we find for the next continuum iteration
        cont_mask_fine = np.ones_like(cont_now)
        cont_mask_fine[pixt_now] = 0.0
        if cont_mask_neg is True:
            pixt_now_neg = detect_peaks(-spec_sub, mph=thresh, mpd=fwhm * 0.75, show=debug_peak_find)
            cont_mask_fine[pixt_now_neg] = 0.0
        # cont_mask is the mask for defining the continuum regions: True is good,  False is bad
        cont_mask = (utils.smooth(cont_mask_fine,mask_odd) > 0.999) & inmask
        # If more than half the spectrum is getting masked than short circuit this masking
        frac_mask = np.sum(np.invert(cont_mask))/float(nspec)
        if (frac_mask > 0.70):
            msgs.warn('Too many pixels masked in spectrum continuum definiton: frac_mask = {:5.3f}'.format(frac_mask) + ' . Not masking....')
            cont_mask = np.ones_like(cont_mask) & inmask
        ngood = np.sum(cont_mask)
        samp_width = np.ceil(ngood/cont_samp).astype(int)
        cont_med = utils.fast_running_median(spec[cont_mask], samp_width)
        if npoly is not None:
            # ToDO robust_poly_fit needs to return minv and maxv as outputs for the fits to be usable downstream
            msk, poly = fitting.robust_polyfit_djs(spec_vec[cont_mask], cont_med, npoly, function='polynomial', maxiter=25,
                                                 upper=3.0, lower=3.0, minx=0.0, maxx=float(nspec-1))
            cont_now = fitting.func_val(poly, spec_vec, 'polynomial')
        else:
            cont_now = np.interp(spec_vec,spec_vec[cont_mask],cont_med)

        if debug & (iter == (niter_cont-1)):
            plt.plot(spec_vec, spec,'k', label='Spectrum')
            #plt.plot(spec_vec, spec*cont_mask,'k', label='Spectrum*cont_mask')
            plt.plot(spec_vec, cont_now,'g',label='continuum')
            plt.plot(spec_vec, spec - cont_now,'b',label='spec-cont')
            plt.plot(spec_vec[cont_mask], spec[cont_mask], color='cyan', markersize=3.0,
                     mfc='cyan', linestyle='None', fillstyle='full',
                     zorder=9, marker='o', label = 'Used for cont')
            plt.plot(spec_vec[np.invert(cont_mask)], spec[np.invert(cont_mask)], color='red', markersize=5.0,
                     mfc='red', linestyle='None', fillstyle='full',
                     zorder=9, marker='o', label = 'masked for cont')
            plt.title(qa_title)
            plt.legend()
            plt.show()

    return cont_now, cont_mask


def detect_lines(censpec, sigdetect=5.0, fwhm=4.0, fit_frac_fwhm=1.25, input_thresh=None,
                 cont_subtract=True, cont_frac_fwhm=1.0, max_frac_fwhm=3.0,
                 min_pkdist_frac_fwhm=0.75, cont_samp=30, nonlinear_counts=1e10, niter_cont=3,
                 nfind=None, bpm=None, verbose=False, debug=False, debug_peak_find=False):
    """
    Extract an arc down the center of the chip and identify
    statistically significant lines for analysis.

    Parameters
    ----------
    censpec : ndarray
      A 1D spectrum to be searched for significant detections

    sigdetect: float, default=20., optional
       Sigma threshold above fluctuations for arc-line detection.
       Arcs are continuum subtracted and the fluctuations are
       computed after continuum subtraction.

    input_thresh: float, str, default= None, optional
       Optionally the user can specify the threhsold that peaks must
       be above to be kept. In this case the sigdetect parameter will
       be ignored. This is most useful for example for cases where
       cont_subtract =False, and the user prefers to determine the
       significance threhsold outside of this routine, rather than
       using this routines defaults to determine the continuum level
       and standard deviation of the continuum subtracted spetrum. If
       a string input of 'None' is set then the code will simply
       return all peaks irrespective of any threshold. This is
       equivalent to setting the mph parameter to None in the
       detect_peaks code.

    fwhm:  float, default = 4.0, optional
       Number of pixels per fwhm resolution element.

    fit_frac_fwhm: float, default 0.5, optional
       Number of pixels that are used in the fits for Gaussian arc
       line centroiding expressed as a fraction of the fwhm parameter

    max_frac_fwhm:  float, default = 2.5, optional
       maximum width allowed for usable arc lines expressed relative
       to the fwhm.

    min_pkdist_frac_fwhm: float, default = 0.75, optional
       minimum allowed separation between peaks expressed relative to
       the fwhm.

    cont_frac_fwhm float, default = 1.0, optional
       width used for masking peaks in the spectrum when the
       continuum is being defined. Expressed as a fraction of the
       fwhm parameter

    cont_subtract: bool, default = True, optional
       If true, the code will continuum subtract the input array by
       iteratively determining the continuum

    cont_samp: float, default = 30.0, optional
       The number of samples across the spectrum used for continuum
       subtraction. Continuum subtraction is done via median
       filtering, with a width of ngood/cont_samp, where ngood is the
       number of good pixels for estimating the continuum (i.e. that
       don't have peaks).

    niter_cont: int, default = 3, optional
       Number of iterations of peak finding, masking, and continuum
       fitting used to define the continuum.

    nonlinear_counts: float, default = 1e10, optional
       Value above which to mask saturated arc lines. This should be
       nonlinear_counts= nonlinear*saturation according to pypeit
       parsets. Default is 1e10 which is to not mask.

    nfind: int, default = None, optional
       Return only the nfind highest significance lines. The default
       is None, which means the code will return all the lines above
       the significance threshold.

    bpm: numpy.ndarray, optional
        Bad-pixel mask for input spectrum. If None, all pixels
        considered good.

    verbose: bool, default = False
       Output more stuff to the screen.

    debug: boolean, default = False
       Make plots showing results of peak finding and final arc lines that are used.

    Returns
    -------
    tampl : ndarray
      The amplitudes of the line detections in the true arc
    tampl_cont : ndarray
      The amplitudes of the line detections in the continuum subtracted arc
    tcent : ndarray
      The centroids of the line detections
    twid : ndarray
      The 1sigma Gaussian widths of the line detections
    centerr : ndarray
      The variance on tcent
    w : ndarray
      An index array indicating which detections are the most reliable.
    arc : ndarray
      The continuum sutracted arc used to find detections.
    nsig : ndarray
      The significance of each line detected relative to the 1sigma
      variation in the continuum subtracted arc in the the line free
      region. Bad lines are assigned a significance of -1, since they
      don't have an amplitude fit
    """

    # Detect the location of the arc lines
    if verbose:
        msgs.info("Detecting lines...isolating the strongest, nonsaturated lines")

    # TODO: Why is this here? Can't the calling function be required to
    # pass a single spectrum?  This is not reflected in the docstring.
    if len(censpec.shape) == 3:
        detns = censpec[:, 0].flatten()
    else:
        detns = censpec.copy()
    detns = detns.astype(np.float)
    xrng = np.arange(detns.size, dtype=np.float)

    if cont_subtract:
        cont_now, cont_mask = iter_continuum(detns, inmask=None if bpm is None else np.invert(bpm),
                                             fwhm=fwhm, niter_cont=niter_cont, cont_samp=cont_samp,
                                             cont_frac_fwhm=cont_frac_fwhm)
    else:
        cont_mask = np.ones(detns.size, dtype=bool)
        cont_now = np.zeros_like(detns)

    arc = detns - cont_now
    if input_thresh is None:
        (mean, med, stddev) = stats.sigma_clipped_stats(arc[cont_mask], sigma_lower=3.0, sigma_upper=3.0)
        thresh = med + sigdetect*stddev
    else:
        med = 0.0
        if isinstance(input_thresh,(float, int)):
            thresh = input_thresh
        elif isinstance(input_thresh, str):
            if input_thresh == 'None':
                thresh = None
        else:
            msgs.error('Unrecognized value for thresh')
        stddev = 1.0

    # Find the peak locations
    pixt = detect_peaks(arc, mph=thresh, mpd=fwhm*min_pkdist_frac_fwhm, show=debug_peak_find)

    # Peak up the centers and determine the widths using a Gaussian fit
    nfitpix = np.round(fit_frac_fwhm*fwhm).astype(int)
    fwhm_max = max_frac_fwhm*fwhm
    tampl_fit, tcent, twid, centerr = fit_arcspec(xrng, arc, pixt, nfitpix)

    # Set the amplitudes using the spectra directly for both the input
    # and continuum-subtracted spectrum.
    # TODO: Why does this interpolate to pixt and not tcent?
    tampl_true = np.interp(pixt, xrng, detns)
    tampl = np.interp(pixt, xrng, arc)

    # Find the lines that meet the following criteria:
    #   - Amplitude is in the linear regime of the detector response
    #   - Center is within the limits of the spectrum
    #   - The Gaussian-fitted center and the center from `detect_lines`
    #     are not different by more than 0.75*FWHM
    #   - Width is finite, greater than 0, and less than FWHM_MAX/2.35
    good = np.invert(np.isnan(twid)) & (twid > 0.0) & (twid < fwhm_max/2.35) & (tcent > 0.0) \
                & (tcent < xrng[-1]) & (tampl_true < nonlinear_counts) \
                & (np.abs(tcent-pixt) < fwhm*0.75)

    # Get the indices of the good measurements
    ww = np.where(good)
    # Compute the significance of each line, set the significance of bad lines to be -1
    nsig = (tampl - med)/stddev

    # If the user requested the nfind most significant peaks have been
    # requested, then grab and return only these lines
    if nfind is not None:
        if nfind > len(nsig):
            msgs.warn('Requested {0} peaks but only found {1}.  '.format(nfind, len(tampl)) +
                      ' Returning all the peaks found.')
        else:
            ikeep = (nsig.argsort()[::-1])[0:nfind]
            tampl_true = tampl_true[ikeep]
            tampl = tampl[ikeep]
            tcent = tcent[ikeep]
            twid = twid[ikeep]
            centerr = centerr[ikeep]
            ww = np.where(good[ikeep])
            nsig = nsig[ikeep]
            good = good[ikeep]

    if debug:
        # NOTE: Uses pixt because apparently tcent can be set to -1 in fit_arcspec
        # TODO: Replace any values of tcent that are -1 with the value of pixt?
        find_lines_qa(arc, pixt, tampl, good, bpm=bpm, thresh=thresh, nonlinear=nonlinear_counts)

    # TODO: Change this to return `good` instead of `ww`
    return tampl_true, tampl, tcent, twid, centerr, ww, arc, nsig

def find_lines_qa(spec, cen, amp, good, bpm=None, thresh=None, nonlinear=None):
    """
    Show a QA plot for the line detection.

    Args:
        spec (`numpy.ndarray`):
            Spectrum used to detect lines
        cen (`numpy.ndarray`):
            Identified line peaks
        amp (`numpy.ndarray`):
            Amplitude of the identified lines.
        good (`numpy.ndarray`):
            Boolean array selecting the good line detections.
        bpm (`numpy.ndarray`, optional):
            The bad-pixel mask for the spectrum. If None, all pixels
            are assumed to be valid.
        thresh (:obj:`float`, optional):
            Threshold value for line detection
        nonlinear (:obj:`float`, optional):
            Threshold for nonlinear detector response.
    """
    # TODO: Could just pull `amp` directly from the spectrum
    # If bpm is provided, the masked pixels are *not* shown
    _spec = np.ma.MaskedArray(spec, mask=np.zeros(spec.size, dtype=bool) if bpm is None else bpm)
    pix = np.arange(_spec.size)
    plt.figure(figsize=(14, 6))
    plt.step(pix, _spec, color='k', where='mid', label='arc', lw=1.0)
    plt.scatter(cen[np.invert(good)], amp[np.invert(good)], marker='+', color='C3', s=50,
                label='bad for tilts')
    plt.scatter(cen[good], amp[good], color='C2', marker='+', s=50, label='good for tilts')
    if thresh is not None:
        plt.axhline(thresh, color='cornflowerblue', linestyle=':', linewidth=2.0,
                    label='threshold', zorder=10)
    if nonlinear is not None and nonlinear < 1e9:
        plt.axhline(nonlinear, color='orange', linestyle='--', linewidth=2.0, label='nonlinear',
                    zorder=10)
    ngood = np.sum(good)
    plt.title('Good Lines = {0},  Bad Lines = {1}'.format(ngood, len(good)-ngood))
    plt.ylim(np.amin(spec), 1.5 * np.amax(spec))
    plt.legend()
    plt.show()

def fit_arcspec(xarray, yarray, pixt, fitp):
    """
    Fit an arc spectrum line

    Args:
        xarray:
        yarray:
        pixt:
        fitp: int
          Number of pixels to fit with

    Returns:

    """

    fitp_even = fitp if fitp % 2 == 0 else fitp + 1
    fit_interval = fitp_even//2

    # Setup the arrays with fit parameters
    sz_p = pixt.size
    sz_a = yarray.size
    b      = np.full(sz_p, -999.0, dtype=float)
    ampl   = np.full(sz_p, -999.0, dtype=float)
    cent   = np.full(sz_p, -999.0, dtype=float)
    widt   = np.full(sz_p, -999.0, dtype=float)
    centerr =np.full(sz_p, -999.0, dtype=float)

    for p in range(sz_p):
        # This interval is always symmetric about the peak
        pmin = pixt[p] - fit_interval
        pmax = pixt[p] + fit_interval + 1
        if pmin < 0:
            pmin = 0
        if pmax > sz_a:
            pmax = sz_a
        if pmin == pmax:
            continue
        if (pmax - pmin) < (fit_interval):
            continue # Probably won't be a good solution
#       JFH Removed below
#       if pixt[p]-pmin <= 1 or pmax-pixt[p] <= 1:
#            continue  # Probably won't be a good solution
        # Fit the gaussian
        try:
            popt, pcov = utils.func_fit(xarray[pmin:pmax], yarray[pmin:pmax], "gaussian", 3, return_errors=True)
            ampl[p] = popt[0]
            cent[p] = popt[1]
            widt[p] = popt[2]
            centerr[p] = pcov[1, 1]
            #popt, pcov = utils.func_fit(xarray[pmin:pmax], yarray[pmin:pmax], "gaussian", 4, return_errors=True)
            #b[p]    = popt[0]
            #ampl[p] = popt[1]
            #cent[p] = popt[2]
            #widt[p] = popt[3]
            #centerr[p] = pcov[2, 2]
        except RuntimeError:
            pass
    return ampl, cent, widt, centerr


def simple_calib_driver(llist, censpec, ok_mask, n_final=5, get_poly=False,
                        sigdetect=10.,
                        IDpixels=None, IDwaves=None, nonlinear_counts=1e10):
    wv_calib = {}
    for slit in ok_mask:
        iwv_calib = simple_calib(llist, censpec[:, slit], n_final=n_final,
                                 get_poly=get_poly, IDpixels=IDpixels, IDwaves=IDwaves,
                                 nonlinear_counts=nonlinear_counts, sigdetect=sigdetect)
        wv_calib[str(slit)] = iwv_calib.copy()
    return wv_calib


def simple_calib(llist, censpec, n_final=5, get_poly=False,
                 IDpixels=None, IDwaves=None, debug=False, sigdetect=10.,
                 nonlinear_counts=1e10):
    """Simple calibration algorithm for longslit wavelengths

    Parameters
    ----------
    llist (Table):
    censpec : ndarray
    get_poly : bool, optional
      Pause to record the polynomial pix = b0 + b1*lambda + b2*lambda**2
    IDpixels : list
    IDwaves : list

    Returns
    -------
    final_fit : dict
      Dict of fit info
    """

    # Extract the arc
    msgs.work("Detecting lines..")
    #tampl, tcent, twid, _, w, yprep, nsig = detect_lines(censpec, nfitpix=nfitpix,
    #                                                     sigdetect=sigdetect,
    #                                                     nonlinear_counts = aparm['nonlinear_counts'])
    tcent, ecent, cut_tcent, icut, spec_cont_sub = wvutils.arc_lines_from_spec(
        censpec, sigdetect=sigdetect, nonlinear_counts=nonlinear_counts)#, debug = debug_peaks)

    # Cut down to the good ones
    tcent = tcent[icut]

    # IDs were input by hand
    # Check that there are at least 4 values
    pixels = np.array(IDpixels) # settings.argflag['arc']['calibrate']['IDpixels'])
    if np.sum(pixels > 0.) < 4:
        msgs.error("Need to give at least 4 pixel values!")
    #
    msgs.info("Using input lines to seed the wavelength solution")
    # Calculate median offset
    mdiff = [np.min(np.abs(tcent-pix)) for pix in pixels]
             #settings.argflag['arc']['calibrate']['IDpixels']]
    med_poff = np.median(np.array(mdiff))
    msgs.info("Will apply a median offset of {:g} pixels".format(med_poff))

    # Match input lines to observed spectrum
    nid = pixels.size
    idx_str = np.ones(nid).astype(int)
    ids = np.zeros(nid)
    idsion = np.array(['     ']*nid)
    gd_str = np.arange(nid).astype(int)
    for jj,pix in enumerate(pixels):
        diff = np.abs(tcent-pix-med_poff)
        if np.min(diff) > 2.:
            msgs.error("No match with input pixel {:g}!".format(pix))
        else:
            imn = np.argmin(diff)
        # Set
        idx_str[jj] = imn
        # Take wavelength from linelist instead of input value
        wdiff = np.abs(llist['wave']-IDwaves[jj]) # settings.argflag['arc']['calibrate']['IDwaves'][jj])
        imnw = np.argmin(wdiff)
        if wdiff[imnw] > 0.015:  # Arbitrary tolerance
            msgs.error("Input IDwaves={:g} is not in the linelist.  Fix".format(
                IDwaves[jj]))
                    #settings.argflag['arc']['calibrate']['IDwaves'][jj]))
        else:
            ids[jj] = llist['wave'][imnw]
            #idsion[jj] = llist['Ion'][imnw]
            msgs.info("Identifying arc line: {:s} {:g}".format(idsion[jj],ids[jj]))

    # Debug
    disp = (ids[-1]-ids[0])/(tcent[idx_str[-1]]-tcent[idx_str[0]])
    final_fit = wv_fitting.iterative_fitting(censpec, tcent, idx_str, ids,
                                          llist, disp, verbose=False, n_final=n_final)
    # Return
    return final_fit



# JFH I think this is all deprecated code as it is in wavecalib.py now
def calib_with_arclines(aparm, spec, ok_mask=None, use_method="general"):
    """Holy grail algorithms for wavelength calibration

    Uses arcparam to guide the analysis

    Parameters
    ----------
    aparm
    spec
    use_method : str, optional

    Returns
    -------
    final_fit : dict
      Dict of fit info
    """
    raise DeprecationWarning("THIS HAS BEEN MOVED INSIDE wavecalib.py")
    assert False

    if ok_mask is None:
        ok_mask = np.arange(spec.shape[1])

    if use_method == "semi-brute":
        final_fit = {}
        for slit in ok_mask:
            best_dict, ifinal_fit = autoid.semi_brute(spec[:, slit], aparm['lamps'], aparm['wv_cen'], aparm['disp'],
                                                      fit_parm=aparm, min_nsig=aparm['min_nsig'], nonlinear_counts= aparm['nonlinear_counts'])
            final_fit[str(slit)] = ifinal_fit.copy()
    elif use_method == "basic":
        final_fit = {}
        for slit in ok_mask:
            status, ngd_match, match_idx, scores, ifinal_fit =\
                autoid.basic(spec[:, slit], aparm['lamps'], aparm['wv_cen'], aparm['disp'], nonlinear_counts = aparm['nonlinear_counts'])
            final_fit[str(slit)] = ifinal_fit.copy()
    else:
        # Now preferred
        arcfitter = autoid.General(spec, aparm['lamps'], ok_mask=ok_mask, fit_parm=aparm, min_nsig=aparm['min_nsig'],
                                   lowest_nsig=aparm['lowest_nsig'], nonlinear_counts = aparm['nonlinear_counts'],
                                   rms_threshold=aparm['rms_threshold'])
        patt_dict, final_fit = arcfitter.get_results()
    return final_fit


def order_saturation(satmask, ordcen, ordwid):
    """
    .. todo::
        Document this!
    """
    sz_y, sz_x = satmask.shape
    sz_o = ordcen.shape[1]

    xmin = ordcen - ordwid
    xmax = ordcen + ordwid + 1
    xmin[xmin < 0] = 0
    xmax[xmax >= sz_x] = sz_x

    ordsat = np.zeros((sz_y, sz_o), dtype=int)
    for o in range(sz_o):
        for y in range(sz_y):
            ordsat[y,o] = (xmax[y,o] > xmin[y,o]) & np.any(satmask[y,xmin[y,o]:xmax[y,o]] == 1)

    return ordsat


def search_for_saturation_edge(a, x, y, sy, dx, satdown, satlevel, mask):
    sx = dx
    localx = a[x+sx,y+sy]
    while True:
        mask[x+sx,y+sy] = True
        sx += dx
        if x+sx > a.shape[0]-1 or x+sx < 0:
            break
        if a[x+sx,y+sy] >= localx/satdown and a[x+sx,y+sy]<satlevel:
            break
        localx = a[x+sx,y+sy]
    return mask


def determine_saturation_region(a, x, y, sy, dy, satdown, satlevel, mask):
    localy = a[x,y+sy]
    while True:
        mask[x,y+sy] = True
        mask = search_for_saturation_edge(a, x, y, sy, 1, satdown, satlevel, mask)
        mask = search_for_saturation_edge(a, x, y, sy, -1, satdown, satlevel, mask)

        sy += dy
        if y+sy > a.shape[1]-1 or y+sy < 0:
            return mask
        if a[x,y+sy] >= localy/satdown and a[x,y+sy] < satlevel:
            return mask
        localy = a[x,y+sy]


def saturation_mask(a, satlevel):
    """
    ... todo::
        Document this!
    """
    mask = np.zeros(a.shape, dtype=bool)
    a_is_saturated = a >= satlevel
    if not np.any(a_is_saturated):
        return mask.astype(int)

    satdown = 1.001
    sz_x, sz_y = a.shape

    for y in range (0,sz_y):
        for x in range(0,sz_x):
            if a_is_saturated[x,y] and not mask[x,y]:
                mask[x,y] = True
                mask = determine_saturation_region(a, x, y, 0, 1, satdown, satlevel, mask)
                mask = determine_saturation_region(a, x, y, -1, -1, satdown, satlevel, mask)

    return mask.astype(int)



