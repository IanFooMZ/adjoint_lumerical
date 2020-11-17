import device as device
import layering as layering
import scale as scale
import sigmoid as sigmoid
import square_blur as square_blur

import skimage.morphology as skim
import networkx as nx

import numpy as np

import time

from LayeredMWIRBridgesBayerFilterParameters import *

def bridges(density, restrictions, costs, topological_correction_value ):
	binary_map = np.greater( density, 0.5 )
	save_binary_map = binary_map.copy()

	pad_density = np.pad(
		density,
		(
			( 1, 1 ), ( 1, 1 )
		),
		mode='constant'
	)

	pad_binary_map = np.greater( pad_density, 0.5 )

	density_shape = density.shape
	width = density_shape[ 0 ]
	height = density_shape[ 1 ]

	pad_costs = np.pad(
		costs,
		(
			( 1, 1 ), ( 1, 1 )
		),
		mode='constant'
	)


	[solid_labels, num_solid_labels] = skim.label( pad_binary_map, neighbors=4, return_num=True )

	if num_solid_labels <= 1:
		return density

	density_graph = nx.MultiDiGraph()
	for x_idx in range( 0, width ):
		for y_idx in range( 0, height ):

			center_node_id = ( x_idx + 1 ) * ( pad_density.shape[ 1 ] ) + ( y_idx + 1 )

			for x_offset in range( 0, 3 ):
				for y_offset in range( 0, 3 ):

					if ( ( x_offset == 1 ) and ( y_offset == 1 ) ) or ( ( np.abs( x_offset - 1 ) + np.abs( y_offset - 1 ) ) > 1 ):
						continue

					next_x_idx = x_idx + x_offset
					next_y_idx = y_idx + y_offset

					if (
						( next_x_idx == 0 ) or
						( next_y_idx == 0 ) or
						( next_x_idx == ( pad_density.shape[ 0 ] - 1 ) ) or
						( next_y_idx == ( pad_density.shape[ 1 ] - 1 ) )
					):
						continue

					next_node_id = next_x_idx * ( pad_density.shape[ 1 ] ) + next_y_idx

					next_density_value = pad_binary_map[ next_x_idx, next_y_idx ]
					cost_value = pad_costs[ next_x_idx, next_y_idx ]

					if next_density_value:
						cost_value = 0

					density_graph.add_edge( center_node_id, next_node_id, weight=cost_value )

	label_to_representative_pt = {}

	for x_idx in range( 0, width ):
		for y_idx in range( 0, height ):
			density_value = pad_density[ 1 + x_idx, 1 + y_idx ]
			component_label = solid_labels[ 1 + x_idx, 1 + y_idx ]

			if ( component_label in label_to_representative_pt.keys() ) or ( not density_value ):
				continue

			label_to_representative_pt[ component_label ] = [ x_idx, y_idx ]

	mst_graph = nx.Graph()

	for label_idx_start in range( 0, num_solid_labels ):
		component_start = 1 + label_idx_start
		source_pt = label_to_representative_pt[ component_start ]
		source_node_id = ( source_pt[ 0 ] + 1 ) * ( pad_density.shape[ 1 ] ) + ( source_pt[ 1 ] + 1 )

		min_path_all = nx.shortest_path(
			density_graph,
			source=source_node_id,
			weight='weight'
		)

		for label_idx_end in range( 1 + label_idx_start, num_solid_labels ):

			component_end = 1 + label_idx_end

			target_pt = label_to_representative_pt[ component_end ]
			target_node_id = ( target_pt[ 0 ] + 1 ) * ( pad_density.shape[ 1 ] ) + ( target_pt[ 1 ] + 1 )

			min_path = min_path_all[ target_node_id ]

			min_path_distance = 0

			for path_idx in range( 1, ( len( min_path ) - 1 ) ):
				node_id = min_path[ path_idx ]

				source_x = int( node_id / pad_density.shape[ 1 ] ) - 1
				source_y = node_id % pad_density.shape[ 1 ] - 1

				min_path_distance += pad_costs[ source_x, source_y ]

			mst_graph.add_edge( component_start, component_end, weight=min_path_distance )


	mst = nx.minimum_spanning_tree( mst_graph )

	mst_edges = nx.edges( mst )

	for edge in mst.edges():
		edge_start, edge_end = edge

		source_pt = label_to_representative_pt[ edge_start ]
		target_pt = label_to_representative_pt[ edge_end ]

		source_node_id = ( source_pt[ 0 ] + 1 ) * ( pad_density.shape[ 1 ] ) + ( source_pt[ 1 ] + 1 )
		target_node_id = ( target_pt[ 0 ] + 1 ) * ( pad_density.shape[ 1 ] ) + ( target_pt[ 1 ] + 1 )


		min_path = nx.shortest_path(
			density_graph,
			source=source_node_id,
			target=target_node_id,
			weight='weight'
		)

		for path_idx in range( 1, ( len( min_path ) - 1 ) ):
			node_id = min_path[ path_idx ]

			source_x = int( node_id / pad_density.shape[ 1 ] ) - 1
			source_y = node_id % pad_density.shape[ 1 ] - 1

			density[ source_x, source_y ] = topological_correction_value
			pad_density[ 1 + source_x, 1 + source_y ] = topological_correction_value
			binary_map[ source_x, source_y ] = True
			pad_binary_map[ 1 + source_x, 1 + source_y ] = True

	restrictions = np.logical_not( np.logical_xor( binary_map, save_binary_map ) )

class LayeredMWIRBridgesBayerFilter(device.Device):

	def __init__(self, size, permittivity_bounds, init_permittivity, num_z_layers, num_free_iterations_between_patches):
		super(LayeredMWIRBridgesBayerFilter, self).__init__(size, permittivity_bounds, init_permittivity)

		self.num_z_layers = num_z_layers
		self.flip_threshold = 0.5
		self.minimum_design_value = 0
		self.maximum_design_value = 1
		self.topological_correction_value = 0.75
		self.num_free_iterations_between_patches = num_free_iterations_between_patches
		self.current_iteration = 0
		self.init_filters_and_variables()
		# set to the 0th epoch value
		self.update_filters( 0 )

		self.update_permittivity()

		self.restrictions = np.ones( self.w[0].shape )

		self.restrictions[ 0 : blur_half_width_voxels, :, : ] = 0
		self.restrictions[ :, 0 : blur_half_width_voxels, : ] = 0
		self.restrictions[ ( self.restrictions.shape[ 0 ]- blur_half_width_voxels ) : ( self.restrictions.shape[ 0 ] ), :, : ] = 0
		self.restrictions[ :, ( self.restrictions.shape[ 1 ] - blur_half_width_voxels ) : ( self.restrictions.shape[ 1 ] ), : ] = 0




	#
	# Override the update_permittivity function so we can handle layer-dependent collapsing along either x- or y-dimensions
	#
	def update_permittivity(self):
		var0 = self.w[0]

		var1 = self.sigmoid_0.forward(var0)
		self.w[1] = var1

		var2 = self.layering_z_1.forward(var1)
		self.w[2] = var2

		var3 = self.max_blur_xy_2.forward(var2)
		self.w[3] = var3

		var4 = self.sigmoid_3.forward(var3)
		self.w[4] = var4

		var5 = self.scale_4.forward(var4)
		self.w[5] = var5


	#
	# Override the update_permittivity function so we can handle layer-dependent collapsing along either x- or y-dimensions
	#
	def fabricate_mask(self):
		var0 = self.w[0]
		print(var0.dtype)
		var1 = self.sigmoid_0.fabricate(var0)
		print(var1.dtype)
		print(var1.shape)
		var2 = self.layering_z_1.forward(var1)
		print(var2.dtype)
		var3 = self.max_blur_xy_2.fabricate(var2)
		var4 = self.sigmoid_3.fabricate(var3)
		return var4

	#
	# Need to also override the backpropagation function
	#
	def backpropagate(self, gradient):
		gradient = self.scale_4.chain_rule(gradient, self.w[5], self.w[4])
		gradient = self.sigmoid_3.chain_rule(gradient, self.w[4], self.w[3])
		gradient = self.max_blur_xy_2.chain_rule(gradient, self.w[3], self.w[2])
		gradient = self.layering_z_1.chain_rule(gradient, self.w[2], self.w[1])
		gradient = self.sigmoid_0.chain_rule(gradient, self.w[1], self.w[0])

		return gradient

	def update_filters(self, epoch):
		self.sigmoid_beta = 0.0625 * (2**epoch)

		self.sigmoid_0 = sigmoid.Sigmoid(self.sigmoid_beta, self.sigmoid_eta)
		self.sigmoid_3 = sigmoid.Sigmoid(self.sigmoid_beta, self.sigmoid_eta)
		self.filters = [self.sigmoid_0, self.layering_z_1, self.max_blur_xy_2, self.sigmoid_3, self.scale_4]

	def init_variables(self):
		super(LayeredMWIRBridgesBayerFilter, self).init_variables()

		self.w[0] = np.multiply(self.init_permittivity, np.ones(self.size, dtype=np.complex))

		self.w[0][ 0 : blur_half_width_voxels, :, : ] = 1
		self.w[0][ :, 0 : blur_half_width_voxels, : ] = 1
		self.w[0][ ( self.w[0].shape[ 0 ] - blur_half_width_voxels ) : ( self.w[0].shape[ 0 ] ), :, : ] = 1
		self.w[0][ :, ( self.w[0].shape[ 1 ] - blur_half_width_voxels ): ( self.w[0].shape[ 1 ] ), : ] = 1


	def init_filters_and_variables(self):
		self.num_filters = 5
		self.num_variables = 1 + self.num_filters

		# Start the sigmoids at weak strengths
		self.sigmoid_beta = 0.0625
		self.sigmoid_eta = 0.5
		self.sigmoid_0 = sigmoid.Sigmoid(self.sigmoid_beta, self.sigmoid_eta)
		self.sigmoid_3 = sigmoid.Sigmoid(self.sigmoid_beta, self.sigmoid_eta)

		x_dimension_idx = 0
		y_dimension_idx = 1
		z_dimension_idx = 2

		z_voxel_layers = self.size[2]
		self.layering_z_1 = layering.Layering(z_dimension_idx, self.num_z_layers)

		alpha = 8
		self.blur_half_width = blur_half_width_voxels
		#
		# This notation is slightly confusing, but it is meant to be the
		# direction you blur when you are on the layer corresponding to x-
		# or y-layering.  So, if you are layering in x, then you blur in y
		# and vice versa.
		#
		self.max_blur_xy_2 = square_blur.SquareBlur(
			alpha,
			[self.blur_half_width, self.blur_half_width, 0])

		scale_min = self.permittivity_bounds[0]
		scale_max = self.permittivity_bounds[1]
		self.scale_4 = scale.Scale([scale_min, scale_max])

		# Initialize the filter chain
		self.filters = [self.sigmoid_0, self.layering_z_1, self.max_blur_xy_2, self.sigmoid_3, self.scale_4]

		self.init_variables()
	


	# In the step function, we should update the permittivity with update_permittivity
	def step(self, gradient, step_size):
		mask_out_restrictions = gradient * self.restrictions

		self.w[0] = self.proposed_design_step(mask_out_restrictions, step_size)

		self.current_iteration += 1

		if ( self.current_iteration % self.num_free_iterations_between_patches ) > 0:
			# Update the variable stack including getting the permittivity at the w[-1] position
			self.update_permittivity()
			return


		#
		# How far do we have to move? Should we include the gradient information in there as well (i.e. - weight also by the gradient?)?
		#
		costs = self.topological_correction_value - self.w[0]

		#
		# For now, let's assume the density does not vary over each layer and that we can just patch up on sublayer in a layer
		# and use that solution for the whole layer
		#

		topological_patch_start = time.time()

		get_layer_idxs = self.layering_z_1.get_layer_idxs( self.w[0].shape )
		for layer in range( 0, self.layering_z_1.num_layers ):
			get_layer_idx = get_layer_idxs[ layer ]
			next_layer_idx = self.w[0].shape[2]

			if layer < ( self.layering_z_1.num_layers - 1 ):
				next_layer_idx = get_layer_idxs[ layer + 1 ]

			bridges(
				self.w[0][ :, :, get_layer_idx ],
				self.restrictions[ :, :, get_layer_idx ],
				costs[ :, :, get_layer_idx ],
				self.topological_correction_value )

			for sublayer_idx in range( 1 + get_layer_idx, next_layer_idx ):
				self.w[0][ :, :, sublayer_idx ] = self.w[0][ :, :, get_layer_idx ]
				self.restrictions[ :, :, sublayer_idx ] = self.restrictions[ :, :, sublayer_idx ]

		topological_patch_elapsed = time.time() - topological_patch_start
		# Update the variable stack including getting the permittivity at the w[-1] position
		self.update_permittivity()

		# The substrate on the top changes this padding
		cur_fabrication_target = self.fabricate_mask()
		pad_cur_fabrication_target = np.pad(
			cur_fabrication_target,
			( ( 1, 1 ), ( 1, 1 ), ( 1, 1 ) ),
			mode='constant'
		)
		pad_cur_fabrication_target[ :, :, pad_cur_fabrication_target.shape[ 2 ] - 1 ] = 1

		[solid_labels, num_solid_labels] = skim.label( pad_cur_fabrication_target, neighbors=4, return_num=True )
		[void_labels, num_void_labels] = skim.label( 1 - pad_cur_fabrication_target, neighbors=8, return_num=True )
		print("Topology Information:")
		print("To patch all of the topology took " + str( topological_patch_elapsed ) + " seconds")
		print("The current number of total solid components is " + str( num_solid_labels ) )
		print("The current number of total void components is " + str( num_void_labels ) )

		for layer in range( 0, self.layering_z_1.num_layers ):
			get_layer_idx = get_layer_idxs[ layer ]
			[solid_labels, num_solid_labels] = skim.label( pad_cur_fabrication_target[ :, :, 1 + get_layer_idx ], neighbors=4, return_num=True )
			[void_labels, num_void_labels] = skim.label( 1 - pad_cur_fabrication_target[ :, :, 1 + get_layer_idx ], neighbors=8, return_num=True )

			print("The current number of solid components on layer " + str( layer ) + " is " + str( num_solid_labels ) )
			print("The current number of void components on layer " + str( layer ) + " is " + str( num_void_labels ) )
		print("\n\n")

		self.restrictions[ 0 : blur_half_width_voxels, :, : ] = 0
		self.restrictions[ :, 0 : blur_half_width_voxels, : ] = 0
		self.restrictions[ ( self.restrictions.shape[ 0 ] - blur_half_width_voxels ) : ( self.restrictions.shape[ 0 ] ), :, : ] = 0
		self.restrictions[ :, ( self.restrictions.shape[ 1 ] - blur_half_width_voxels ) : ( self.restrictions.shape[ 1 ] ), : ] = 0



	def convert_to_binary_map(self, variable):
		return np.greater(variable, self.mid_permittivity)
