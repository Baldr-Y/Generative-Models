import tensorflow as tf 
import numpy as np
import time
import datetime

import modules as model
from options import Options
from utils import Dataset

class GAN(object):

	def __init__(self, image, opts, reuse=False, is_training=False):
		self.image = image
		self.reuse = reuse
		self.is_training = is_training
		self.opts = opts
		self.dims = opts.d_dims
		self.pred = self.Discriminator()
		self.generated_imgs = self.Generator()

	def Discriminator(self):
		"""
		Discriminator part of GAN
		"""

		with tf.variable_scope("discriminator"):
			conv1 = model.conv2d(self.image, [5,5,3,self.dims], 2, "conv1", is_training, False, self.reuse)
			conv2 = model.conv2d(conv1, [3,3,self.dims,self.dims*2], 2, "conv2", is_training, True, self.reuse)
			conv3 = model.conv2d(conv2, [3,3,self.dims*2,self.dims*4], 2, "conv3", is_training, True, self.reuse)
			full4 = model.fully_connected(tf.reshape(conv3, [self.opts.batch_size, -1]), 1, is_training, None, "full4", False, self.reuse)
		return tf.nn.softmax(full4), full4

	def Generator(self):
		"""
		Generator part of GAN
		"""

		with tf.variable_scope("generator"):
			fulll1 = model.fully_connected(self.z, self.dims*4*4*4, is_training, tf.nn.relu, "full1", False, self.reuse)
			dconv2 = model.deconv(tf.reshape(fulll1, [-1, 4, 4, self.dims*4]), [8, 8, self.dims*2, self.dims*4], 2, "dconv2", is_training, False)
			dconv3 = model.deconv(dconv2, [16, 16, self.dims, self.dims*2], 2, "dconv3", is_training, False)
			dconv4 = model.deconv(dconv3, [32, 32, self.dims, 3], 2, "dconv4", is_training, False)
		return tf.nn.tanh(dconv4)

	def loss(self):
		pass

	def train(self):
		pass


class VAE(object):
	"""
	Variatinoal Autoencoder
	"""

	def __init__(self, opts, is_training):
		self.h = opts.image_size_h
		self.w = opts.image_size_w
		self.c = opts.channels
		self.images = tf.placeholder(tf.float32, [None, self.h, self.w, self.c], "images") # 32x32x3
		self.lr = tf.placeholder(tf.float32, [], "learning_rate")
		self.is_training = is_training
		self.opts = opts
		self.mean, self.std = self.encoder()

		unit_gauss = tf.random_normal([self.opts.batch_size, self.opts.encoder_vec_size])
		self.z = self.mean + self.std * unit_gauss
		self.logits, self.generated_imgs = self.decoder(self.z)

		self.l1, self.l2 = self.loss()
		self.l = self.l1+self.l2

		self.sess = tf.Session()
		self.optimizer = tf.train.AdamOptimizer(self.lr).minimize(self.l)
		self.init = tf.global_variables_initializer()
		self.saver = tf.train.Saver(write_version=tf.train.SaverDef.V2)
		tf.summary.scalar('Encoder loss', self.l1)
		tf.summary.scalar('Decoder loss', self.l2)
		tf.summary.scalar('Total loss', self.l)
		tf.summary.scalar('Learning Rate', self.lr)
		self.summaries = tf.summary.merge_all()
		self.writer = tf.summary.FileWriter(self.opts.root_dir+self.opts.summary_dir, self.sess.graph)

	def encoder(self):
		"""
		Encoder to generate the `latent vector`
		"""

		dims = self.opts.g_dims
		code_len = self.opts.encoder_vec_size
		if self.opts.dataset == "CIFAR":
			with tf.variable_scope("encoder"):
				conv1 = model.conv2d(self.images, [3, 3, self.c, dims], 2, "conv1", alpha=0.01) # 16x16x64
				conv2 = model.conv2d(conv1, [3, 3, dims, dims*2], 2, "conv2", alpha=0.01) # 8x8x128
				conv3 = model.conv2d(conv2, [3, 3, dims * 2, dims * 4], 2, "conv3", alpha=0.01) # 4x4x256
				conv4 = model.conv2d(conv3, [3, 3, dims * 4, dims * 8], 2, "conv4", alpha=0.01) # 2x2x512
				conv3_flat = tf.reshape(conv4, [-1, 2*2*512])
				mean = model.fully_connected(conv3_flat, code_len, self.is_training, None, "full3_mean", use_leak=True, bias_constant=0.01) # 40
				stds = model.fully_connected(conv3_flat, code_len, self.is_training, None, "full3_stds", use_leak=True, bias_constant=0.01) # 40
		else:
			with tf.variable_scope("encoder"):
				dims = 16
				conv1 = model.conv2d(self.images, [3, 3, self.c, dims], 2, "conv1", alpha=0.2, use_leak=True, bias_constant=0.01) # 14x14x16
				conv2 = model.conv2d(conv1, [3, 3, dims, dims * 2], 2, "conv2", alpha=0.2, use_leak=True, bias_constant=0.01) # 7x7x32
				conv2d_flat = tf.reshape(conv2, [-1, 7*7*32])
				mean = model.fully_connected(conv2d_flat, code_len, self.is_training, None, "full3_mean", use_leak=True, bias_constant=0.01) # 40
				stds = model.fully_connected(conv2d_flat, code_len, self.is_training, None, "full3_stds", use_leak=True, bias_constant=0.01) # 40

		return mean, stds

	def decoder(self, z):
		"""
		Generate images from the `latent vector`
		"""

		dims = self.opts.g_dims
		if self.opts.dataset == "CIFAR":
			with tf.variable_scope("decoder"):
				full1 = model.fully_connected(z, 2*2*512, self.is_training, tf.nn.relu, "full1", use_leak=True, alpha=0.2) # 4x4x256
				dconv2 = model.deconv(tf.reshape(full1, [-1, 2, 2, 512]), [3,3,256,512], [self.opts.batch_size, 4, 4, 256], 2, "dconv2", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 8x8x128
				dconv3 = model.deconv(dconv2, [3,3,128,256], [self.opts.batch_size, 8, 8, 128], 2, "dconv3", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 16x16x64
				dconv4 = model.deconv(dconv3, [3,3,64,128], [self.opts.batch_size, 16, 16, 64], 2, "dconv4", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 16x16x64
				output = model.deconv(dconv4, [3,3,3,64], [self.opts.batch_size, self.h, self.w, self.c], 2, "output", initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 32x32x3
				probs = tf.nn.sigmoid(output)
		else:
			with tf.variable_scope("decoder"):
				full1 = model.fully_connected(z, 7*7*32, self.is_training, tf.nn.relu, "full1")
				dconv2 = model.deconv(tf.reshape(full1, [-1, 7, 7, 32]), [3,3,16,32],\
									  [self.opts.batch_size, 14, 14, 16], 2, "dconv2", tf.nn.relu,\
									  initializer=tf.truncated_normal_initializer(stddev=0.02),\
									  bias_constant=0.01)
				output = model.deconv(dconv2, [3,3,1,16], [self.opts.batch_size, 28, 28, 1],\
									  2, "output", None, initializer=tf.truncated_normal_initializer(stddev=0.02),\
									  bias_constant=0.01)
				probs = tf.nn.sigmoid(output)

		return tf.reshape(output, [-1, self.h*self.w*self.c]), tf.reshape(probs, [-1, self.h*self.w*self.c])

	def loss(self):
		img_flat = tf.reshape(self.images, [-1, self.h*self.w*self.c])

		encoder_loss = 0.5 * tf.reduce_sum(tf.square(self.mean)+tf.square(self.std)-tf.log(tf.square(self.std))-1., 1)
		decoder_loss = -tf.reduce_sum(img_flat * tf.log(1e-8 + self.generated_imgs) + (1-img_flat) * tf.log(1e-8 + 1 - self.generated_imgs),1)
		
		encoder_loss = self.opts.D_lambda * tf.reduce_mean(encoder_loss)
		decoder_loss = self.opts.G_lambda * tf.reduce_mean(decoder_loss)
		return encoder_loss, decoder_loss

	def train(self):
		utils = Dataset(self.opts)
		lr = self.opts.base_lr
		self.sess.run(self.init)
		for iteration in xrange(1, self.opts.MAX_iterations):
			batch_num = 0
			for batch_begin, batch_end in zip(xrange(0, self.opts.train_size, self.opts.batch_size), \
				xrange(self.opts.batch_size, self.opts.train_size, self.opts.batch_size)):
				begin_time = time.time()
				batch_imgs = utils.load_batch(batch_begin, batch_end)
				feed_dict = {self.images:batch_imgs, self.lr:lr}
				_, l1, l2, summary = self.sess.run([self.optimizer, self.l1, self.l2, self.summaries], feed_dict=feed_dict)

				batch_num += 1
				self.writer.add_summary(summary, iteration * (self.opts.train_size/self.opts.batch_size) + batch_num)
				if batch_num % self.opts.display == 0:
					rem_time = (time.time() - begin_time) * self.opts.MAX_iterations * (self.opts.train_size/self.opts.batch_size)
					log  = '-'*20
					log += '\nIteration: {}/{}|'.format(iteration, self.opts.MAX_iterations)
					log += 'Batch Number: {}/{}|'.format(batch_num, self.opts.train_size/self.opts.batch_size)
					log += 'Batch Time: {}\n'.format(time.time() - begin_time)
					log += ' Remaining Time: {:0>8}\n'.format(datetime.timedelta(seconds=rem_time))
					log += ' Learning Rate: {}\n'.format(lr)
					log += ' Encoder Loss: {}\n'.format(l1)
					log += ' Decoder Loss: {}\n'.format(l2)
					print log
				if iteration % self.opts.lr_decay == 0 and batch_num == 1:
					lr *= self.opts.lr_decay_factor
				if iteration % self.opts.ckpt_frq == 0 and batch_num == 1:
					self.saver.save(self.sess, self.opts.root_dir+self.opts.ckpt_dir+"{}_{}_{}".format(iteration, lr, l1+l2))
				if iteration % self.opts.generate_frq == 0 and batch_num == 1:
					generate_imgs = utils.test_images
					imgs = self.sess.run(self.generated_imgs, feed_dict={self.images:generate_imgs, self.lr:lr})
					if self.opts.dataset == "CIFAR":
						imgs = np.reshape(imgs, (self.opts.test_size, 3, 32, 32)).transpose(0, 2, 3, 1)
					else:
						imgs = np.reshape(imgs, (self.opts.test_size, 28, 28))
					tf.summary.image('Generated image', imgs[0])
					utils.save_batch_images(imgs, [self.opts.grid_h, self.opts.grid_w], str(iteration)+".jpg", True)

	def test(self, image):
		latest_ckpt = tf.train.latest_checkpoint(self.opts.ckpt_dir)
		tf.saver.restore(self.sess, latest_ckpt)
