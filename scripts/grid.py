#!/usr/bin/env python

import argparse
parser = argparse.ArgumentParser(description="Interact with the raw" \
    " spectral libraries, including convolving with an instrumental profile.")
parser.add_argument("--create", action="store_true", help="Create a downsampled grid convolved with the instrumental profile, following the parameter ranges specified in config.yaml.")
parser.add_argument("--plot", action="store_true", help="plot all of the spectra in the newly downsampled grid to check whether the process worked properly.")
parser.add_argument("--pcreate", action="store_true", help="Create the grid for Piece of Cake.")

args = parser.parse_args()

import Starfish

if args.create:

    from Starfish.grid_tools import HDF5Creator

    # Specifically import the grid interface and instrument that we want.
    instrument = eval("Starfish.grid_tools." + Starfish.data["instruments"][0])()
    mygrid = eval("Starfish.grid_tools." + Starfish.data["grid_name"])()

    creator = HDF5Creator(mygrid, Starfish.grid["hdf5_path"], instrument,
                          ranges=Starfish.grid["parrange"])

    creator.process_grid()

if args.plot:

    # Check to make sure the file exists
    import os
    if not os.path.exists(Starfish.grid["hdf5_path"]):
        print("HDF5 file does not yet exist. Please run `grid.py create` first.")
        import sys
        sys.exit()

    import multiprocessing as mp
    import matplotlib.pyplot as plt
    from Starfish.grid_tools import HDF5Interface
    interface = HDF5Interface()

    par_fluxes = zip(interface.grid_points, interface.fluxes)

    # Define the plotting function
    def plot(par_flux):
        par, flux = par_flux
        fig, ax = plt.subplots(nrows=1, figsize=(8, 6))
        ax.plot(interface.wl, flux)
        ax.set_xlabel(r"$\lambda$ [AA]")
        ax.set_ylabel(r"$f_\lambda$")
        fmt = "=".join(["{:.2f}" for i in range(len(Starfish.parname))])
        name = fmt.format(*[p for p in par])
        fig.savefig(Starfish.config["plotdir"] + "g" + name + ".png")

        plt.close("all")

    p = mp.Pool(mp.cpu_count())
    p.map(plot, par_fluxes)

if args.pcreate:

    from Starfish.grid_tools import HDF5Creator

    # Specifically import the grid interface and instrument that we want.
    instrument = eval("Starfish.grid_tools." + Starfish.data["instruments"][0])()
    mygrid = eval("Starfish.grid_tools." + Starfish.data["grid_name"])()

    creator = HDF5Creator(mygrid, Starfish.grid["hdf5_path"], instrument, ranges=Starfish.grid["parrange"], key_name=Starfish.config["pCake"]["key_name"], vsinis=Starfish.config["vsinis"])

    creator.process_grid()
