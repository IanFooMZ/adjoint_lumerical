import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from LayeredLithographyIRPolarizationParameters import *
import LayeredLithographyIRPolarizationDevice

import imp
imp.load_source( "lumapi", "/central/home/gdrobert/Develompent/lumerical/2020a/api/python/lumapi.py" )
import lumapi

import functools
import h5py
import matplotlib.pyplot as plt
import numpy as np
import time



def intensity_from_field( E ):
	intensity = np.sum( np.conj( E ) * E, axis=0 )
	return intensity

def contrast_fom( E_out_parallel, E_out_orthogonal ):
	I_parallel = intensity_from_field( E_out_parallel )
	I_orthogonal = intensity_from_field( E_out_orthogonal )

	contrast = ( I_parallel - I_orthogonal ) / ( I_parallel + I_orthogonal )

	return contrast

def dipole_weightings( E_out_parallel, E_out_orthogonal ):
	field_shape = E_out_parallel.shape
	num_wavelengths = field_shape[ 1 ]

	x_parallel_weighting = np.zeros( num_wavelengths, dtype=np.complex )
	y_parallel_weighting = np.zeros( num_wavelengths, dtype=np.complex )
	x_orthogonal_weighting = np.zeros( num_wavelengths, dtype=np.complex )
	y_orthogonal_weighting = np.zeros( num_wavelengths, dtype=np.complex )

	for wl_idx in range( 0, num_wavelengths ):

		I_parallel = intensity_from_field( E_out_parallel )
		I_orthogonal = intensity_from_field( E_out_orthogonal )

		difference = I_parallel - I_orthogonal
		total = I_parallel + I_orthogonal

		x_parallel_weighting[ wl_idx ] = ( total[ wl_idx ] * np.conj( E_out_parallel[ 0, wl_idx ] ) - difference[ wl_idx ] * np.conj( E_out_parallel[ 0, wl_idx ] ) ) / total[ wl_idx ]**2
		# can also write as:
		# x_parallel_weighting = np.conj( E_out_parallel[ 0 ] ) * ( total[ wl_idx ] - difference[ wl_idx ] ) / total[ wl_idx ]**2
		y_parallel_weighting[ wl_idx ] = ( total[ wl_idx ] * np.conj( E_out_parallel[ 1, wl_idx ] ) - difference[ wl_idx ] * np.conj( E_out_parallel[ 1, wl_idx ] ) ) / total[ wl_idx ]**2

		x_orthogonal_weighting[ wl_idx ] = ( -total[ wl_idx ] * np.conj( E_out_orthogonal[ 0, wl_idx ] ) - difference[ wl_idx ] * np.conj( E_out_orthogonal[ 0, wl_idx ] ) ) / total[ wl_idx ]**2
		y_orthogonal_weighting[ wl_idx ] = ( -total[ wl_idx ] * np.conj( E_out_orthogonal[ 1, wl_idx ] ) - difference[ wl_idx ] * np.conj( E_out_orthogonal[ 1, wl_idx ] ) ) / total[ wl_idx ]**2


	return [ np.array( [ x_parallel_weighting, y_parallel_weighting ] ), np.array( [ x_orthogonal_weighting, y_orthogonal_weighting ] ) ]



#
# Create FDTD hook
#
fdtd_hook = lumapi.FDTD()

#
# Create project folder and save out the parameter file for documentation for this optimization
#
python_src_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
projects_directory_location = os.path.abspath(os.path.join(os.path.dirname(__file__), '../projects/'))
projects_directory_location += "/" + project_name

if not os.path.isdir(projects_directory_location):
	os.mkdir(projects_directory_location)

fdtd_hook.newproject()
fdtd_hook.save(projects_directory_location + "/optimization")

shutil.copy2(python_src_directory + "/LayeredLithographyIRPolarizationParameters.py", projects_directory_location + "/LayeredLithographyIRPolarizationParameters.py")

#
# Set up the FDTD region and mesh
#
fdtd = fdtd_hook.addfdtd()
fdtd['x span'] = fdtd_region_size_lateral_um * 1e-6
fdtd['y span'] = fdtd_region_size_lateral_um * 1e-6
fdtd['z max'] = fdtd_region_maximum_vertical_um * 1e-6
fdtd['z min'] = fdtd_region_minimum_vertical_um * 1e-6
fdtd['mesh type'] = 'uniform'
fdtd['define x mesh by'] = 'number of mesh cells'
fdtd['define y mesh by'] = 'number of mesh cells'
fdtd['define z mesh by'] = 'number of mesh cells'
fdtd['mesh cells x'] = fdtd_region_minimum_lateral_voxels
fdtd['mesh cells y'] = fdtd_region_minimum_lateral_voxels
fdtd['mesh cells z'] = fdtd_region_minimum_vertical_voxels
fdtd['simulation time'] = fdtd_simulation_time_fs * 1e-15
fdtd['background index'] = background_index

# design_mesh = fdtd_hook.addmesh()
# design_mesh['name'] = 'design_override_mesh'
# design_mesh['x span'] = device_size_lateral_um * 1e-6
# design_mesh['y span'] = device_size_lateral_um * 1e-6
# design_mesh['z max'] = device_vertical_maximum_um * 1e-6
# design_mesh['z min'] = device_vertical_minimum_um * 1e-6
# design_mesh['dx'] = mesh_spacing_um * 1e-6
# design_mesh['dy'] = mesh_spacing_um * 1e-6
# design_mesh['dz'] = mesh_spacing_um * 1e-6


#
# General polarized source information
#
xy_phi_rotations = [0, 90]
xy_names = ['x', 'y']


#
# Add a TFSF plane wave forward source at normal incidence
#
forward_sources = []

for xy_idx in range(0, 2):
	forward_src = fdtd_hook.addtfsf()
	forward_src['name'] = 'forward_src_' + xy_names[xy_idx]
	forward_src['angle phi'] = xy_phi_rotations[xy_idx]
	forward_src['direction'] = 'Backward'
	forward_src['x span'] = lateral_aperture_um * 1e-6
	forward_src['y span'] = lateral_aperture_um * 1e-6
	forward_src['z max'] = src_maximum_vertical_um * 1e-6
	forward_src['z min'] = src_minimum_vertical_um * 1e-6
	forward_src['wavelength start'] = lambda_min_um * 1e-6
	forward_src['wavelength stop'] = lambda_max_um * 1e-6

	forward_sources.append(forward_src)

#
# Place dipole adjoint sources at the focal plane that can ring in both
# x-axis and y-axis
#
adjoint_sources = []

for adj_src_idx in range(0, num_adjoint_sources):
	adjoint_sources.append([])
	for xy_idx in range(0, 2):
		adj_src = fdtd_hook.adddipole()
		adj_src['name'] = 'adj_src_' + str(adj_src_idx) + xy_names[xy_idx]
		adj_src['x'] = adjoint_x_positions_um[adj_src_idx] * 1e-6
		adj_src['y'] = adjoint_y_positions_um[adj_src_idx] * 1e-6
		adj_src['z'] = adjoint_vertical_um * 1e-6
		adj_src['theta'] = 90
		adj_src['phi'] = xy_phi_rotations[xy_idx]
		adj_src['wavelength start'] = lambda_min_um * 1e-6
		adj_src['wavelength stop'] = lambda_max_um * 1e-6

		adjoint_sources[adj_src_idx].append(adj_src)

#
# Set up the volumetric electric field monitor inside the design region.  We will need this compute
# the adjoint gradient
#
design_efield_monitor = fdtd_hook.addprofile()
design_efield_monitor['name'] = 'design_efield_monitor'
design_efield_monitor['monitor type'] = '3D'
design_efield_monitor['x span'] = device_size_lateral_um * 1e-6
design_efield_monitor['y span'] = device_size_lateral_um * 1e-6
design_efield_monitor['z max'] = device_vertical_maximum_um * 1e-6
design_efield_monitor['z min'] = device_vertical_minimum_um * 1e-6
design_efield_monitor['override global monitor settings'] = 1
design_efield_monitor['use wavelength spacing'] = 1
design_efield_monitor['use source limits'] = 1
design_efield_monitor['frequency points'] = num_design_frequency_points
design_efield_monitor['output Hx'] = 0
design_efield_monitor['output Hy'] = 0
design_efield_monitor['output Hz'] = 0

#
# Set up adjoint point monitors to get electric field strength at focus spots.  This will allow us to
# compute the figure of merit as well as weight the adjoint simulations properly in calculation of the
# gradient.
#
focal_monitors = []

for adj_src in range(0, num_adjoint_sources):
	focal_monitor = fdtd_hook.addpower()
	focal_monitor['name'] = 'focal_monitor_' + str(adj_src)
	focal_monitor['monitor type'] = 'point'
	focal_monitor['x'] = adjoint_x_positions_um[adj_src] * 1e-6
	focal_monitor['y'] = adjoint_y_positions_um[adj_src] * 1e-6
	focal_monitor['z'] = adjoint_vertical_um * 1e-6
	focal_monitor['override global monitor settings'] = 1
	focal_monitor['use wavelength spacing'] = 1
	focal_monitor['use source limits'] = 1
	focal_monitor['frequency points'] = num_design_frequency_points

	focal_monitors.append(focal_monitor)


#
# Add SiO2 at the top
#
sio2_top = fdtd_hook.addrect()
sio2_top['name'] = 'sio2_top'
sio2_top['x span'] = fdtd_region_size_lateral_um * 1e-6
sio2_top['y span'] = fdtd_region_size_lateral_um * 1e-6
sio2_top['z min'] = device_vertical_maximum_um * 1e-6
sio2_top['z max'] = fdtd_region_maximum_vertical_um * 1e-6
sio2_top['index'] = index_sio2

air_bottom = fdtd_hook.addrect()
air_bottom['name'] = 'air_bottom'
air_bottom['x span'] = fdtd_region_size_lateral_um * 1e-6
air_bottom['y span'] = fdtd_region_size_lateral_um * 1e-6
air_bottom['z min'] = fdtd_region_minimum_vertical_um * 1e-6
air_bottom['z max'] = device_vertical_minimum_um * 1e-6
air_bottom['index'] = index_air


#
# Add device region and create device permittivity
#
design_import = fdtd_hook.addimport()
design_import['name'] = 'design_import'
design_import['x span'] = device_size_lateral_um * 1e-6
design_import['y span'] = device_size_lateral_um * 1e-6
design_import['z max'] = device_vertical_maximum_um * 1e-6
design_import['z min'] = device_vertical_minimum_um * 1e-6

bayer_filter_size_voxels = np.array([device_voxels_lateral, device_voxels_lateral, device_voxels_vertical])
bayer_filter = LayeredLithographyIRPolarizationDevice.LayeredLithographyIRPolarizationDevice(
	bayer_filter_size_voxels,
	[min_device_permittivity, max_device_permittivity],
	init_permittivity_0_1_scale,
	num_vertical_layers,
	spacer_size_voxels,
	[index_air**2, index_silicon**2],
	max_binarize_movement,
	desired_binarize_change)


# bayer_filter.set_design_variable( np.random.random( bayer_filter.get_design_variable().shape ) )
# bayer_filter.step(
# 	np.random.random( bayer_filter.get_design_variable().shape ),
# 	0.01,
# 	True,
# 	projects_directory_location
# )
# sys.exit(0)

# bayer_filter.set_design_variable( np.load(projects_directory_location + "/cur_design_variable.npy") )

bayer_filter_region_x = 1e-6 * np.linspace(-0.5 * device_size_lateral_um, 0.5 * device_size_lateral_um, device_voxels_lateral)
bayer_filter_region_y = 1e-6 * np.linspace(-0.5 * device_size_lateral_um, 0.5 * device_size_lateral_um, device_voxels_lateral)
bayer_filter_region_z = 1e-6 * np.linspace(device_vertical_minimum_um, device_vertical_maximum_um, device_voxels_vertical)

#
# Disable all sources in the simulation, so that we can selectively turn single sources on at a time
#
def disable_all_sources():
	fdtd_hook.switchtolayout()

	for xy_idx in range(0, 2):
		(forward_sources[xy_idx]).enabled = 0

	for adj_src_idx in range(0, num_adjoint_sources):
		for xy_idx in range(0, 2):
			(adjoint_sources[adj_src_idx][xy_idx]).enabled = 0

#
# Consolidate the data transfer functionality for getting data from Lumerical FDTD process to
# python process.  This is much faster than going through Lumerical's interop library
#
def get_monitor_data(monitor_name, monitor_field):
	lumerical_data_name = "monitor_data_" + monitor_name + "_" + monitor_field
	extracted_data_name = lumerical_data_name + "_data"
	data_transfer_filename = projects_directory_location + "/data_transfer_" + monitor_name + "_" + monitor_field

	command_read_monitor = lumerical_data_name + " = getresult(\'" + monitor_name + "\', \'" + monitor_field + "\');"
	command_extract_data = extracted_data_name + " = " + lumerical_data_name + "." + monitor_field + ";"
	command_save_data_to_file = "matlabsave(\'" + data_transfer_filename + "\', " + extracted_data_name + ");"

	lumapi.evalScript(fdtd_hook.handle, command_read_monitor)
	lumapi.evalScript(fdtd_hook.handle, command_extract_data)

	# start_time = time.time()

	lumapi.evalScript(fdtd_hook.handle, command_save_data_to_file)
	monitor_data = {}
	load_file = h5py.File(data_transfer_filename + ".mat")

	monitor_data = np.array(load_file[extracted_data_name])

	# end_time = time.time()

	# print("\nIt took " + str(end_time - start_time) + " seconds to transfer the monitor data\n")

	return monitor_data

def get_complex_monitor_data(monitor_name, monitor_field):
	data = get_monitor_data(monitor_name, monitor_field)
	return (data['real'] + np.complex(0, 1) * data['imag'])

#
# Set up some numpy arrays to handle all the data we will pull out of the simulation.
#
forward_e_fields = {}
focal_data = {}

figure_of_merit_evolution = np.zeros((num_epochs, num_iterations_per_epoch))
figure_of_merit_per_focal_spot_evolution = np.zeros((num_epochs, num_iterations_per_epoch, num_focal_spots))
parallel_intensity_per_focal_spot_evolution = np.zeros((num_epochs, num_iterations_per_epoch, num_focal_spots, num_design_frequency_points))
orthogonal_intensity_per_focal_spot_evolution = np.zeros((num_epochs, num_iterations_per_epoch, num_focal_spots, num_design_frequency_points))

step_size_evolution = np.zeros((num_epochs, num_iterations_per_epoch))
average_design_variable_change_evolution = np.zeros((num_epochs, num_iterations_per_epoch))
max_design_variable_change_evolution = np.zeros((num_epochs, num_iterations_per_epoch))

step_size_start = 0.001

if start_epoch > 0:
	design_variable_reload = np.load( projects_directory_location + '/cur_design_variable_' + str( start_epoch - 1 ) + '.npy' )
	bayer_filter.set_design_variable( design_variable_reload )

#
# Run the optimization
#
for epoch in range(start_epoch, num_epochs):
	bayer_filter.update_filters(epoch)

	for iteration in range(0, num_iterations_per_epoch):
		print("Working on epoch " + str(epoch) + " and iteration " + str(iteration))

		fdtd_hook.switchtolayout()
		cur_permittivity = np.flip( bayer_filter.get_permittivity(), axis=2 )
		fdtd_hook.select("design_import")
		fdtd_hook.importnk2(np.sqrt(cur_permittivity), bayer_filter_region_x, bayer_filter_region_y, bayer_filter_region_z)


		#
		# Step 1: Run the forward optimization for both x- and y-polarized plane waves.
		#
		for xy_idx in range(0, 2):
			disable_all_sources()
			(forward_sources[xy_idx]).enabled = 1
			fdtd_hook.run()

			forward_e_fields[xy_names[xy_idx]] = get_complex_monitor_data(design_efield_monitor['name'], 'E')

			focal_data[xy_names[xy_idx]] = []
			for adj_src_idx in range(0, num_adjoint_sources):
				focal_data[xy_names[xy_idx]].append(get_complex_monitor_data(focal_monitors[adj_src_idx]['name'], 'E'))


		shutil.copy( projects_directory_location + "/optimization.fsp", projects_directory_location + "/optimization_start_epoch_" + str( epoch ) + ".fsp" )

		#
		# Step 2: Compute the figure of merit
		#
		figure_of_merit_per_focal_spot = []
		parallel_intensity_per_focal_spot = []
		orthogonal_intensity_per_focal_spot = []
		for focal_idx in range(0, num_focal_spots):
			compute_fom = 0

			analyzer_vector = jones_sorting_vectors[ focal_idx ]
			orthogonal_vector = jones_orthogonal_vectors[ focal_idx ]

			create_forward_parallel_response = analyzer_vector[ 0 ] * focal_data[ 'x' ][ focal_idx ] + analyzer_vector[ 1 ] * focal_data[ 'y' ][ focal_idx ]
			create_forward_orthogonal_response = orthogonal_vector[ 0 ] * focal_data[ 'x' ][ focal_idx ] + orthogonal_vector[ 1 ] * focal_data[ 'y' ][ focal_idx ]

			for spectral_idx in range( 0, num_design_frequency_points ):
				paraxial_parallel_forward = create_forward_parallel_response[ :, spectral_idx, 0, 0, 0 ]
				paraxial_parallel_forward[ 2 ] = 0

				paraxial_orthogonal_forward = create_forward_orthogonal_response[ :, spectral_idx, 0, 0, 0 ]
				paraxial_orthogonal_forward[ 2 ] = 0

				parallel_intensity_per_focal_spot_evolution[ epoch, iteration, focal_idx, spectral_idx ] = (
					intensity_from_field( paraxial_parallel_forward )
				)

				orthogonal_intensity_per_focal_spot_evolution[ epoch, iteration, focal_idx, spectral_idx ] = (
					intensity_from_field( paraxial_orthogonal_forward )
				)

				compute_fom += ( 1 + contrast_fom(
					paraxial_parallel_forward,
					paraxial_orthogonal_forward ) )

			figure_of_merit_per_focal_spot.append( compute_fom )


		figure_of_merit_per_focal_spot = np.array(figure_of_merit_per_focal_spot)

		# So we are currently weighting by focal spot but not by individual frequency
		# This might be why you are getting three peaks in the color splitting version
		#
		# Figure of merit per focal spot, these contrasts can be negative.  The most negative can be -1.  We will add one to each one above 
		performance_weighting = (2. / num_focal_spots) - figure_of_merit_per_focal_spot**2 / np.sum(figure_of_merit_per_focal_spot**2)
		performance_weighting -= np.min(performance_weighting)
		performance_weighting /= np.sum(performance_weighting)

		figure_of_merit = np.sum(figure_of_merit_per_focal_spot)
		figure_of_merit_evolution[epoch, iteration] = figure_of_merit

		np.save(projects_directory_location + "/figure_of_merit.npy", figure_of_merit_evolution)
		np.save(projects_directory_location + "/figure_of_merit_per_focal_spot.npy", figure_of_merit_per_focal_spot_evolution)
		np.save(projects_directory_location + "/parallel_intensity.npy", parallel_intensity_per_focal_spot_evolution)
		np.save(projects_directory_location + "/orthogonal_intensity.npy", orthogonal_intensity_per_focal_spot_evolution)

		#
		# Step 3: Run all the adjoint optimizations for both x- and y-polarized adjoint sources and use the results to compute the
		# gradients for x- and y-polarized forward sources.
		#
		cur_permittivity_shape = cur_permittivity.shape
		reversed_field_shape = [cur_permittivity_shape[2], cur_permittivity_shape[1], cur_permittivity_shape[0]]
		xy_polarized_gradients = [ np.zeros(reversed_field_shape, dtype=np.complex), np.zeros(reversed_field_shape, dtype=np.complex) ]
		accumulate_gradient = np.zeros(reversed_field_shape, dtype=np.complex)

		for adj_src_idx in range(0, num_adjoint_sources):
			polarizations = polarizations_focal_plane_map[adj_src_idx]

			analyzer_vector = jones_sorting_vectors[ adj_src_idx ]
			orthogonal_vector = jones_orthogonal_vectors[ adj_src_idx ]

			create_forward_parallel_response = analyzer_vector[ 0 ] * focal_data[ 'x' ][ focal_idx ] + analyzer_vector[ 1 ] * focal_data[ 'y' ][ focal_idx ]
			create_forward_orthogonal_response = orthogonal_vector[ 0 ] * focal_data[ 'x' ][ focal_idx ] + orthogonal_vector[ 1 ] * focal_data[ 'y' ][ focal_idx ]

			create_forward_parallel_fields = analyzer_vector[ 0 ] * forward_e_fields[ 'x' ] + analyzer_vector[ 1 ] * forward_e_fields[ 'y' ]
			create_forward_orthogonal_fields = orthogonal_vector[ 0 ] * forward_e_fields[ 'x' ] + orthogonal_vector[ 1 ] * forward_e_fields[ 'y' ]

			gradient_performance_weight = performance_weighting[adj_src_idx]

			adjoint_e_fields = []
			for xy_idx in range(0, 2):
				disable_all_sources()
				(adjoint_sources[adj_src_idx][xy_idx]).enabled = 1
				fdtd_hook.run()

				adjoint_e_fields.append(
					get_complex_monitor_data(design_efield_monitor['name'], 'E'))


			#
			# For now, just try and increase the contrast.  We will want to make sure overall transmission is high too, which can
			# be added in as another fiugre of merit.
			#
			adjoint_phase_weightings = dipole_weightings( np.squeeze( create_forward_parallel_response ), np.squeeze( create_forward_orthogonal_response ) )

			for spectral_idx in range( 0, num_design_frequency_points ):
				for xy_idx in range( 0, 2 ):

					accumulate_gradient += np.sum(
						gradient_performance_weight *
						adjoint_phase_weightings[ 0 ][ xy_idx, spectral_idx ] *
						adjoint_e_fields[ xy_idx ][ :, spectral_idx, :, :, : ] *
						create_forward_parallel_fields[ :, spectral_idx, :, :, : ],
						axis=0
					)

					accumulate_gradient += np.sum(
						gradient_performance_weight *
						adjoint_phase_weightings[ 1 ][ xy_idx, spectral_idx ] *
						adjoint_e_fields[ xy_idx ][ :, spectral_idx, :, :, : ] *
						create_forward_orthogonal_fields[ :, spectral_idx, :, :, : ],
						axis=0
					)


		#
		# Step 4: Step the design variable.
		#
		device_gradient = 2 * np.real( accumulate_gradient )
		# Because of how the data transfer happens between Lumerical and here, the axes are ordered [z, y, x] when we expect them to be
		# [x, y, z].  For this reason, we swap the 0th and 2nd axes to get them into the expected ordering.
		device_gradient = np.swapaxes(device_gradient, 0, 2)

		design_gradient = bayer_filter.backpropagate(device_gradient)

		max_change_design = epoch_start_permittivity_change_max
		min_change_design = epoch_start_permittivity_change_min

		if num_iterations_per_epoch > 1:

			max_change_design = (
				epoch_end_permittivity_change_max +
				(num_iterations_per_epoch - 1 - iteration) * (epoch_range_permittivity_change_max / (num_iterations_per_epoch - 1))
			)

			min_change_design = (
				epoch_end_permittivity_change_min +
				(num_iterations_per_epoch - 1 - iteration) * (epoch_range_permittivity_change_min / (num_iterations_per_epoch - 1))
			)


		cur_design_variable = bayer_filter.get_design_variable()

		step_size = step_size_start

		check_last = False
		last = 0

		while True:
			proposed_design_variable = cur_design_variable + step_size * design_gradient
			proposed_design_variable = np.maximum(
										np.minimum(
											proposed_design_variable,
											1.0),
										0.0)

			difference = np.abs(proposed_design_variable - cur_design_variable)
			max_difference = np.max(difference)

			if (max_difference <= max_change_design) and (max_difference >= min_change_design):
				break
			elif (max_difference <= max_change_design):
				step_size *= 2
				if (last ^ 1) and check_last:
					break
				check_last = True
				last = 1
			else:
				step_size /= 2
				if (last ^ 0) and check_last:
					break
				check_last = True
				last = 0

		step_size_start = step_size

		last_design_variable = cur_design_variable.copy()
		#
		# todo: fix this in other files! the step already does the backpropagation so you shouldn't
		# pass it an already backpropagated gradient!  Sloppy, these files need some TLC and cleanup!
		#
		enforce_binarization = False
		if epoch >= binarization_start_epoch:
			enforce_binarization = True
		device_gradient = np.flip( device_gradient, axis=2 )
		bayer_filter.step(-device_gradient, step_size, enforce_binarization, projects_directory_location)
		cur_design_variable = bayer_filter.get_design_variable()

		average_design_variable_change = np.mean( np.abs(cur_design_variable - last_design_variable) )
		max_design_variable_change = np.max( np.abs(cur_design_variable - last_design_variable) )

		step_size_evolution[epoch][iteration] = step_size
		average_design_variable_change_evolution[epoch][iteration] = average_design_variable_change
		max_design_variable_change_evolution[epoch][iteration] = max_design_variable_change

		np.save(projects_directory_location + '/device_gradient.npy', device_gradient)
		np.save(projects_directory_location + '/design_gradient.npy', design_gradient)
		np.save(projects_directory_location + "/step_size_evolution.npy", step_size_evolution)
		np.save(projects_directory_location + "/average_design_change_evolution.npy", average_design_variable_change_evolution)
		np.save(projects_directory_location + "/max_design_change_evolution.npy", max_design_variable_change_evolution)
		np.save(projects_directory_location + "/cur_design_variable.npy", cur_design_variable)
		np.save(projects_directory_location + "/cur_design_variable_" + str( epoch ) + ".npy", cur_design_variable)

	shutil.copy( projects_directory_location + "/optimization.fsp", projects_directory_location + "/optimization_end_epoch_" + str( epoch ) + ".fsp" )

