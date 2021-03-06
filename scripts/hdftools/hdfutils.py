#!/usr/bin/env python
import os
import numpy as np
import Starfish.constants as C
from astropy.table import Table
from astropy.io import ascii
import sys

import triangle

#Base package for all HDF tools

#Basically, import this package and all of the argparsing, file commenting, should be done already.

#Scripts like hdfmultiple, hdfcat, hdfplot, and hdfregion should all use this common core.

import argparse
parser = argparse.ArgumentParser(description="Measure statistics across multiple chains.")
parser.add_argument("--glob", help="Do something on this glob. Must be given as a quoted expression to avoid shell "
                                  "expansion.")
parser.add_argument("--ftype", default="stellar", help="What type of flatchains do we have?")
#parser.add_argument("--dir", action="store_true", help="Concatenate all of the flatchains stored within run* "
#                                                       "folders in the current directory. Designed to collate runs
# from a JobArray.")
parser.add_argument("--outdir", default="mcmcplot", help="Output directory to contain all plots.")
parser.add_argument("--output", default="combined.hdf5", help="Output HDF5 file.")

parser.add_argument("--lnprob", help="The HDF5 file containing the lnprobability chains.")
parser.add_argument("--files", nargs="+", help="The HDF5 files containing the MCMC samples, separated by whitespace.")

parser.add_argument("--burn", type=int, default=0, help="How many samples to discard from the beginning of the chain for burn in.")
parser.add_argument("--thin", type=int, default=1, help="Thin the chain by this factor. E.g., --thin 100 will take "
                                                        "every 100th sample.")
parser.add_argument("--keep", type=int, default=0, help="How many samples to keep from the end of the chain, "
                                                        "the beginning of the chain will be for burn in.")
parser.add_argument("--range", nargs=2, help="start and end ranges for chain plot, separated by WHITESPACE")


parser.add_argument("--chain", action="store_true", help="Make a plot of the position of the chains.")
parser.add_argument("-t", "--triangle", action="store_true", help="Make a triangle (staircase) plot of the parameters.")
parser.add_argument("--stellar_params", nargs="*", default="all", help="A list of which stellar parameters to plot, "
                                                                       "separated by WHITESPACE. Default is to plot all.")
parser.add_argument("--gelman", action="store_true", help="Compute the Gelman-Rubin convergence statistics.")

parser.add_argument("--acor", action="store_true", help="Calculate the autocorrelation of the chain")
parser.add_argument("--acor-window", type=int, default=50, help="window to compute acor with")

parser.add_argument("--cov", action="store_true", help="Estimate the covariance between two parameters.")
parser.add_argument("--ndim", type=int, help="How many dimensions to use for estimating the 'optimal jump'.")
parser.add_argument("--paper", action="store_true", help="Change the figure plotting options appropriate for the "
                                                         "paper.")
parser.add_argument("--replicate", action="store_true", help="Repeat the (converged) chains for the paper plot to "
                                                             "fill in the appearance of the histogram.")

args = parser.parse_args()

#Check to see if outdir exists.
if not os.path.exists(args.outdir):
    os.makedirs(args.outdir)

args.outdir += "/"

import h5py

#Plot kw
label_dict = {"temp":r"$T_{\rm eff}\;[{\rm K}]$", "logg":r"$\log g$", "Z":r"$[{\rm Fe}/{\rm H}]$",
              "alpha":r"$[\alpha/{\rm Fe}]$",
              "vsini":r"$v \sin i\;[{\rm km\;s}^{-1}]$",
              "vz":r"$v_z$", "vz1":r"$v_z1$", "vz2":r"$v_z2$", "vz3":r"$v_z3$",
              "logOmega":r"$\log \Omega$",
              "logOmega1":r"$\log{10} \Omega 1$",
              "logOmega2":r"$\log{10} \Omega 2$",
              "logOmega3":r"$\log{10} \Omega 3$",
              "logc0":r"$\log_{10} c_0$", "c1":r"$c_0$", "c2":r"$c_1$", "c3":r"$c_3$",
              "sigAmp":r"$b$", "logAmp":r"$\log_{10} a_{\rm g}$", "l":r"$l$",
              "h":r"$h$", "loga":r"$\log_{10} a$", "mu":r"$\mu$", "sigma":r"$\sigma$"}

# Region-matching code
import re
p_cheb = re.compile(".*c\d*", re.IGNORECASE)
p_region = re.compile("r\d*.*", re.IGNORECASE)

def is_param(str, type):
    '''
    Return true if the string is of this type of parameter.
    '''
    if type == "stellar":
        if str in C.stellar_set:
            return True
        else:
            return False

    elif type == "cheb":
        m = p_cheb.match(str)
        if m:
            return True
        else:
            return False

    elif type == "cov":
        if str in C.cov_global_parameters:
            return True
        else:
            return False

    elif type == "region":
        m = p_region.match(str)
        if m:
            return True
        else:
            return False

    elif type == "all":
        # Match all characters
        return True

    else:
        print("Unknown type")
        return False


#Additionally, there should be an object for each flatchain, that stores param_tuple and samples
class Flatchain:
    '''
    Simply stores variable names and the samples
    '''
    def __init__(self, id, param_tuple, samples):
        #Strip "/" from id and replace it with "_"
        self.id = id.replace("/", "-")
        self.param_tuple = param_tuple
        self.samples = samples

    def clip_param(self, clip_params):
        '''
        Clip the sample chain to include only those parameters in the param_list
        '''
        index_arr = []
        for param in clip_params:
            #What index is this parameter in parameter tuple?
            index_arr += [self.param_tuple.index(param)]
        index_arr = np.array(index_arr)
        self.samples = self.samples[:, index_arr]
        self.param_tuple = tuple([self.param_tuple[index] for index in index_arr])

    @classmethod
    def open(cls, fname, type="stellar"):
        '''
        Create a flatchain from an HDF5 filepath.

        :param fname: filename of HDF5 to open
        :param regions: True/False: discard any regions for now.
        '''

        hdf5 = h5py.File(fname, "r")

        #Get the first dset
        #id, value = lsthdf5.items()
        ilist = list(hdf5.items())
        if len(ilist) > 1:
            id, dset = "stellar", hdf5["stellar"]
        else:
            id, dset = ilist[0]

        param_tuple = dset.attrs["parameters"]
        param_tuple = tuple([param.strip("'() ") for param in param_tuple.split(",")])
        samples = dset[:]

        #Design a function which will take parameter names, a type, and return a boolean array of whether these match

        #If we have regions, then separate them and discard for now.
        ind = np.array([is_param(param, type) for param in param_tuple], dtype='bool')
        param_tuple = tuple([param_tuple[i] for i in range(len(param_tuple)) if ind[i]])

        samples = samples[:,ind].copy()

        flatchain = cls(id, param_tuple, samples)
        hdf5.close()

        return flatchain

    @classmethod
    def from_dset(cls, id, dset):
        '''
        Create from an HDF5 dataset
        '''
        param_tuple = dset.attrs["parameters"]
        param_tuple = tuple([param.strip("'() ") for param in param_tuple.split(",")])
        samples = dset[:]

        #If we have regions, then separate them and discard for now.
        ind = np.array([not_region(param) for param in param_tuple], dtype='bool')
        param_tuple = tuple([param_tuple[i] for i in range(len(param_tuple)) if ind[i]])

        return cls(id, param_tuple, samples[:,ind])

    @property
    def shape(self):
        return self.samples.shape

    def clip_range(self, start, end):
        self.samples = self.samples[start, end]

    def burn_thin(self, burn=0, thin=1):
        '''
        Burn this many samples from the start of the chain.
        '''
        assert burn < self.shape[0]
        print("{} burning by {} and thinning by {}".format(self.id, burn, thin))
        self.samples = self.samples[burn::thin]

    def keep(self, num):
        '''
        Keep this many samples from the end of the chain.
        '''
        assert num < self.shape[0]
        self.samples = self.samples[-num:]


    def __eq__(self, other):
        '''
        Test equality between this flatchain and another (ie, can we concatenate them together)
        '''
        return (self.param_tuple == other.param_tuple) and (self.shape == other.shape)

def gelman_rubin(samplelist):
    '''
    Given a list of flatchains from separate runs (that already have burn in cut and have been trimmed, if desired),
    compute the Gelman-Rubin statistics in Bayesian Data Analysis 3, pg 284.

    If you want to compute this for fewer parameters, then truncate the list before feeding it in.
    '''


    full_iterations = len(samplelist[0])
    assert full_iterations % 2 == 0, "Number of iterations must be even. Try cutting off a different number of burn " \
                                     "in samples."
    shape = samplelist[0].shape
    #make sure all the chains have the same number of iterations
    for flatchain in samplelist:
        assert len(flatchain) == full_iterations, "Not all chains have the same number of iterations!"
        assert flatchain.shape == shape, "Not all flatchains have the same shape!"

    #make sure all chains have the same number of parameters.

    #Following Gelman,
    # n = length of split chains
    # i = index of iteration in chain
    # m = number of split chains
    # j = index of which chain
    n = full_iterations//2
    m = 2 * len(samplelist)
    nparams = samplelist[0].shape[-1] #the trailing dimension of a flatchain

    #Block the chains up into a 3D array
    chains = np.empty((n, m, nparams))
    for k, flatchain in enumerate(samplelist):
        chains[:,2*k,:] = flatchain[:n]  #first half of chain
        chains[:,2*k + 1,:] = flatchain[n:] #second half of chain

    #Now compute statistics
    #average value of each chain
    avg_phi_j = np.mean(chains, axis=0, dtype="f8") #average over iterations, now a (m, nparams) array
    #average value of all chains
    avg_phi = np.mean(chains, axis=(0,1), dtype="f8") #average over iterations and chains, now a (nparams,) array

    B = n/(m - 1.0) * np.sum((avg_phi_j - avg_phi)**2, axis=0, dtype="f8") #now a (nparams,) array

    s2j = 1./(n - 1.) * np.sum((chains - avg_phi_j)**2, axis=0, dtype="f8") #now a (m, nparams) array

    W = 1./m * np.sum(s2j, axis=0, dtype="f8") #now a (nparams,) arary

    var_hat = (n - 1.)/n * W + B/n #still a (nparams,) array
    std_hat = np.sqrt(var_hat)

    R_hat = np.sqrt(var_hat/W) #still a (nparams,) array


    data = Table({   "Value": avg_phi,
                     "Uncertainty": std_hat},
                 names=["Value", "Uncertainty"])

    print(data)

    ascii.write(data, sys.stdout, Writer = ascii.Latex, formats={"Value":"%0.3f", "Uncertainty":"%0.3f"}) #

    #print("Average parameter value: {}".format(avg_phi))
    #print("std_hat: {}".format(np.sqrt(var_hat)))
    print("R_hat: {}".format(R_hat))

    if np.any(R_hat >= 1.1):
        print("You might consider running the chain for longer. Not all R_hats are less than 1.1.")

def GR_list(flatchainList):
    '''
    Given a list of FlatchainTrees, step through each key in turn (following the structure of the first
    FlatchainTree), and pull out the relevant chains to perform the GR diagnostic.
    '''
    gelman_rubin([flatchain.samples for flatchain in flatchainList])

def cat_list(file, flatchainList):
    '''
    Given a list of flatchains, concatenate all of these and write them to a single HDF5 file,
    with optional burn in and thin.
    '''
    #Write this out to the new file
    print("Opening", file)
    hdf5 = h5py.File(file, "w")

    cat = np.concatenate([flatchain.samples for flatchain in flatchainList], axis=0)

    id = flatchainList[0].id
    param_tuple = flatchainList[0].param_tuple

    dset = hdf5.create_dataset(id, cat.shape, compression='gzip', compression_opts=9)
    dset[:] = cat
    dset.attrs["parameters"] = "{}".format(param_tuple)
    #ftree0 = flatchainTreeList[0]
    #keys = ftree0.flatchains_dict.keys() #list of all possible base keys

    #List of flatchain dicts
    #fchain_dicts = [ftree.flatchains_dict for ftree in flatchainTreeList]



    # for key in keys:
    #     if "region" not in key:
    #         dsetkey = key.replace("-", "/")
    #         print("\nWriting", dsetkey)
    #         params = ftree0.flatchains_dict[key].param_tuple
    #         cat = np.concatenate([fchain_dict[key].samples for fchain_dict in fchain_dicts], axis=0)
    #
    #         dset = hdf5.create_dataset(dsetkey, cat.shape, compression='gzip', compression_opts=9)
    #         dset[:] = cat
    #         dset.attrs["parameters"] = "{}".format(params)

    hdf5.close()


def plot(flatchain, base=args.outdir, triangle_plot=args.triangle, chain_plot=args.chain,
         lnprob=args.lnprob, clip_stellar='all', format=".pdf"):
    '''
    Make a bunch of plots to diagnose how the run went.
    '''

    import matplotlib
    matplotlib.rc("font", size=16)

    #Navigate the flatchain tree, and each time we encounter a flatchain, plot it.

    if flatchain.id == "stellar" and clip_stellar != "all":
        flatchain.clip_param(clip_stellar)

    params = flatchain.param_tuple
    samples = flatchain.samples
    labels = [label_dict.get(key, "unknown") for key in params]

    figure = triangle.corner(samples, labels=labels, quantiles=[0.16, 0.5, 0.84],
                             show_titles=True, title_args={"fontsize": 16}, plot_contours=True,
                             plot_datapoints=False)
    figure.savefig(base + flatchain.id + format)


def plot_paper(flatchain, base=args.outdir, triangle_plot=args.triangle, chain_plot=args.chain,
         lnprob=args.lnprob, clip_stellar='all', format=".pdf"):
    '''
    Make a bunch of plots to diagnose how the run went.
    '''

    import matplotlib
    matplotlib.rc("font", size=8)
    #matplotlib.rc("axes", labelpad=10)
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter as FSF
    from matplotlib.ticker import MaxNLocator

    #Navigate the flatchain tree, and plot just the stellar parameters
    #flatchain = [flatchain for flatchain in flatchainTree.flatchains if flatchain.id == "stellar"][0]

    #Just assume that we're getting the stellar flatchain.
    assert flatchain.id == "stellar", "Paper plotting mode only available for Stellar parameters at the moment."

    if clip_stellar != "all":
        flatchain.clip_param(clip_stellar)

    params = flatchain.param_tuple
    samples = flatchain.samples

    labels = [label_dict.get(key, "unknown") for key in params]

    K = len(labels)
    fig, axes = plt.subplots(K, K, figsize=(3.5, 3.35))

    figure = triangle.corner(samples, labels=labels, # quantiles=[0.16, 0.5, 0.84],
                             show_titles=False, title_args={"fontsize": 8}, plot_contours=True,
                             plot_datapoints=False, fig=fig)
    if K == 3:
        figure.subplots_adjust(left=0.13, right=0.87, top=0.95, bottom=0.16)
    if K == 4:
        figure.subplots_adjust(left=0.13, right=0.87, top=0.95, bottom=0.15)

    axes[-1,0].xaxis.set_major_formatter(FSF("%.0f"))

    if K == 4:
        #Yaxis
        for ax in axes[:, 0]:
            ax.yaxis.set_label_coords(-0.48, 0.5)
        for ax in axes[-1, :]:
            ax.xaxis.set_label_coords(0.5, -0.48)

        axes[-1,-1].xaxis.set_major_locator(MaxNLocator(nbins=5, prune='lower'))

    if K == 3:
        #Yaxis
        for ax in axes[:, 0]:
            ax.yaxis.set_label_coords(-0.40, 0.5)
        for ax in axes[-1, :]:
            ax.xaxis.set_label_coords(0.5, -0.39)

        for ax in axes[:, 1]:
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4, prune='lower'))

        axes[1, 0].yaxis.set_major_locator(MaxNLocator(nbins=5))


    figure.savefig(base + flatchain.id + format)
    figure.savefig(base + flatchain.id + ".svg")

def plot_walkers(filename, samples, lnprobs=None, start=0, end=-1, labels=None):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    # majorLocator = MaxNLocator(nbins=4)
    ndim = len(samples[0, :])
    sample_num = np.arange(len(samples[:,0]))
    sample_num = sample_num[start:end]
    samples = samples[start:end]
    plt.rc("ytick", labelsize="x-small")

    if lnprobs is not None:
        fig, ax = plt.subplots(nrows=ndim + 1, sharex=True)
        ax[0].plot(sample_num, lnprobs[start:end])
        ax[0].set_ylabel("lnprob")
        for i in range(0, ndim):
            ax[i+1].plot(sample_num, samples[:,i])
            ax[i+1].yaxis.set_major_locator(MaxNLocator(nbins=6, prune="both"))
            if labels is not None:
                ax[i+1].set_ylabel(labels[i])

    else:
        fig, ax = plt.subplots(nrows=ndim, sharex=True)
        for i in range(0, ndim):
            ax[i].plot(sample_num, samples[:,i])
            ax[i].yaxis.set_major_locator(MaxNLocator(nbins=6, prune="both"))
            if labels is not None:
                ax[i].set_ylabel(labels[i])

    ax[-1].set_xlabel("Sample number")
    fig.subplots_adjust(hspace=0)
    fig.savefig(filename)
    plt.close(fig)


if args.chain:
    if args.range is not None:
        start, end = [int(el) for el in args.range]
    else:
        start=0
        end=-1

    if args.lnprob:
        plot_walkers(args.outdir + "stellar_chain_pos.png", stellar, stellarLnprob, start=start, end=end)
    else:
        plot_walkers(args.outdir + "stellar_chain_pos.png", stellar, start=start, end=end)

    #Now plot the orders
    for i, order in enumerate(orders):
        orderList = ordersList[i]
        cheb = orderList[0]

        if args.lnprob:
            orderListLnprob = ordersListLnprob[i]
            chebLnprob = orderListLnprob[0]
            plot_walkers(args.outdir + "{}_cheb_chain_pos.png".format(order), cheb, chebLnprob, start=start, end=end)

        else:
            plot_walkers(args.outdir + "{}_cheb_chain_pos.png".format(order), cheb, start=start, end=end)

        if yes_cov:
            cov = orderList[1]
            plot_walkers(args.outdir + "{}_cov_chain_pos.png".format(order), cov, start=start, end=end)

            if args.lnprob:
                covLnprob = orderListLnprob[1]
                plot_walkers(args.outdir + "{}_cov_chain_pos.png".format(order), cov, covLnprob, start=start,
                             end=end)
            else:
                plot_walkers(args.outdir + "{}_cov_chain_pos.png".format(order), cov, start=start, end=end)

    if yes_region:
        #Now plot the regions
        for i, order in enumerate(orders):
            orderList = ordersListRegions[i]

            if args.lnprob:
                orderListLnprob = ordersListRegionsLnprob[i]

                #Now cycle through all regions in this list?
                for j, (samples, lnprob) in enumerate(zip(orderList, orderListLnprob)):
                    plot_walkers(args.outdir + "{}_cov_region{:0>2}_chain_pos.png".format(order, j), samples,
                                 lnprobs=lnprob, start=start, end=end)

            else:
                #Now cycle through all regions in this list?
                for j, samples in enumerate(orderList):
                    plot_walkers(args.outdir + "{}_cov_region{:0>2}_chain_pos.png".format(order, j), samples,
                                 start=start, end=end)

def estimate_covariance(flatchain):

    print("Parameters {}".format(flatchain.param_tuple))
    samples = flatchain.samples
    cov = np.cov(samples, rowvar=0)

    #Now try correlation coefficient
    cor = np.corrcoef(samples, rowvar=0)
    print("Correlation coefficient")
    print(cor)

    print("Standard deviation")
    std_dev = np.sqrt(np.diag(cov))
    print(std_dev)

    print("'Optimal' jumps")
    if args.ndim:
        d = args.ndim
    else:
        d = samples.shape[1]
    print(2.38/np.sqrt(d) * std_dev)

#Now that all of the structures have been declared, do the initialization stuff.

if args.glob:
    from glob import glob
    files = glob(args.glob)
elif args.files:
    files = args.files
else:
    import sys
    sys.exit("Must specify either --glob or --files")

#Because we are impatient and want to compute statistics before all the jobs are finished, there may be some
# directories that do not have a flatchains.hdf5 file
flatchainList = []
for file in files:
    try:
        flatchainList.append(Flatchain.open(file, type=args.ftype))
    except OSError as e:
        print("{} does not exist, skipping. Or error {}".format(file, e))

print("Using a total of {} flatchains".format(len(flatchainList)))

#Check to see if burn or thin were specified
if args.burn and args.thin:
    for fchain in flatchainList:
        fchain.burn_thin(args.burn, args.thin)
