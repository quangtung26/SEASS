import os
import json
import utils
import torch
import argparse
from layers import Seq2SeqAttention
from Model import Model
from utils import BatchManager, load_data
import logging

parser = argparse.ArgumentParser(description='Selective Encoding for Abstractive Sentence Summarization in DyNet')

parser.add_argument('--n_epochs', type=int, default=5, help='Number of epochs [default: 3]')
parser.add_argument('--n_train', type=int, default=3803900,
					help='Number of training data (up to 3803957 in gigaword) [default: 3803957]')
parser.add_argument('--n_valid', type=int, default=189651,
					help='Number of validation data (up to 189651 in gigaword) [default: 189651])')
parser.add_argument('--batch_size', type=int, default=64, help='Mini batch size [default: 32]')
parser.add_argument('--emb_dim', type=int, default=300, help='Embedding size [default: 256]')
parser.add_argument('--hid_dim', type=int, default=512, help='Hidden state size [default: 256]')
parser.add_argument('--maxout_dim', type=int, default=2, help='Maxout size [default: 2]')
parser.add_argument('--model_file', type=str, default='./models/params_0.pkl')
args = parser.parse_args()


logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
	filename='log/train.log',
	filemode='w'
)

# define a new Handler to log to console as well
console = logging.StreamHandler()
# optional, set the logging level
console.setLevel(logging.INFO)
# set a format which is the same for console use
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)


model_dir = './models'
if not os.path.exists(model_dir):
	os.mkdir(model_dir)


def calc_loss(logits, batchY, model):
	# loss = model.loss_function(logits.transpose(1,2), batchY)
	loss = model.loss_layer(logits.transpose(1, 2), batchY)
	return loss


def validate(valid_x, valid_y, model):
	batch_x = valid_x.next_batch().cuda()
	batch_y = valid_y.next_batch().cuda()
	with torch.no_grad():
		logits = model(batch_x, batch_y)
		loss = calc_loss(logits, batch_y[:,1:], model) # exclude start token
		return loss


def run_step(valid_x, valid_y, model):
	batch_x = valid_x.next_batch().cuda()
	batch_y = valid_y.next_batch().cuda()
	logits = model(batch_x, batch_y)
	loss = calc_loss(logits, batch_y[:,1:], model) # exclude start token
	return loss


def train(train_x, train_y, valid_x, valid_y, model, optimizer, scheduler, epochs=1):
	logging.info("Start to train...")
	n_batches = train_x.steps
	for epoch in range(epochs):
		for idx in range(n_batches):
			optimizer.zero_grad()

			loss = run_step(train_x, train_y, model)
			loss.backward()  # do not use retain_graph=True
			del loss
			torch.nn.utils.clip_grad_value_(model.parameters(), 5)

			optimizer.step()
			# scheduler.step()

			if (idx + 1) % 10 == 0:
				train_loss = loss.cpu().detach().numpy()
				with torch.no_grad():
					valid_loss = run_step(valid_x, valid_y, model)
				logging.info('epoch %d, step %d, training loss = %f, validation loss = %f'
							 % (epoch, idx + 1, train_loss, valid_loss))

		model.cpu()
		torch.save(model.state_dict(), os.path.join(model_dir, 'params_%d.pkl' % epoch))
		logging.info('Model saved in dir %s' % model_dir)
		model.cuda()
		# model.embedding_look_up.to(torch.device("cpu"))


def main():
	print(args)

	N_EPOCHS = args.n_epochs
	N_TRAIN = args.n_train
	N_VALID = args.n_valid
	BATCH_SIZE = args.batch_size
	EMB_DIM = args.emb_dim
	HID_DIM = args.hid_dim
	MAXOUT_DIM = args.maxout_dim

	data_dir = 'sumdata/'
	TRAIN_X = 'sumdata/train/train.article.txt'
	TRAIN_Y = 'sumdata/train/train.title.txt'
	VALID_X = 'sumdata/train/valid.article.filter.txt'
	VALID_Y = 'sumdata/train/valid.title.filter.txt'
	# TRAIN_X = 'sumdata/biendata/train_content.txt'
	# TRAIN_Y = 'sumdata/biendata/train_title.txt'
	# VALID_X = 'sumdata/biendata/valid_content.txt'
	# VALID_Y = 'sumdata/biendata/valid_title.txt'

	vocab_file = os.path.join(data_dir, "vocab.json")
	if not os.path.exists(vocab_file):
		utils.build_vocab_from_embeddings([TRAIN_X, TRAIN_Y], vocab_file)
	vocab = json.load(open(vocab_file))

	train_x = BatchManager(load_data(TRAIN_X, vocab, N_TRAIN), BATCH_SIZE)
	train_y = BatchManager(load_data(TRAIN_Y, vocab, N_TRAIN), BATCH_SIZE)

	valid_x = BatchManager(load_data(VALID_X, vocab, N_VALID), BATCH_SIZE*2)
	valid_y = BatchManager(load_data(VALID_Y, vocab, N_VALID), BATCH_SIZE*2)

	# model = Seq2SeqAttention(len(vocab), EMB_DIM, HID_DIM, BATCH_SIZE, vocab, max_trg_len=25).cuda()
	model = Model(vocab, out_len=25, emb_dim=EMB_DIM, hid_dim=HID_DIM).cuda()
	# model.embedding_look_up.to(torch.device("cpu"))

	model_file = args.model_file
	if os.path.exists(model_file):
		model.load_state_dict(torch.load(model_file))
		logging.info('Load model parameters from %s' % model_file)

	optimizer = torch.optim.Adam(model.parameters(), lr=0.0003)
	scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=20000, gamma=0.3)

	train(train_x, train_y, valid_x, valid_y, model, optimizer, scheduler, N_EPOCHS)


if __name__ == '__main__':
	main()

