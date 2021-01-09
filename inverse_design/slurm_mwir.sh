#!/bin/bash

#SBATCH -A Faraon_Computing
#SBATCH --time=0:10:00
#SBATCH --nodes=5
#SBATCH -n=32
#SBATCH -N=1
#SBATCH --ntasks-per-node=8
#SBATCH --qos=normal
#SBATCH --mem-per-cpu=30G

source activate fdtd

xvfb-run --server-args="-screen 0 1280x1024x24" python LayeredMWIRBridgesBayerFilterOptimization.py 10 > stdout_mwir.log 2> stderr_mwir.log

exit $?
