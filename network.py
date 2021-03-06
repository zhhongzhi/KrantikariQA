'''
    Calls various components files to create a models/network. Also provides various functionalities to train and predict.
'''
import numpy as np

import os, sys
os.environ['QT_QPA_PLATFORM']='offscreen'

import torch
import traceback

sys.path.append('/data/priyansh/conda/fastai')
import fastai
from fastai.text import *

# from qelos_core.scripts.lcquad.corerank import FlatEncoder

# Local imports
import components as com
from utils import tensor_utils as tu

class Model(object):
    """
        Boilerplate class which helps others have some common functionality.
        These are made with some debugging/loading and with corechains in mind

    """

    def prepare_save(self):
        pass

    def load_from(self, location):
        # Pull the data from disk
        model_dump = torch.load(location)

        # Load parameters
        for key in self.prepare_save():
            key[1].load_state_dict(model_dump[key[0]])

    def get_parameter_sum(self):

        sum = 0
        for model in self.prepare_save():

            model_sum = 0
            for x in list(model[1].parameters()):

                model_sum += np.sum(x.data.cpu().numpy().flatten())

            sum += model_sum

        return sum

    def freeze_layer(self,layer):
        for params in layer.parameters():
            params.requires_grad = False

    def unfreeze_layer(self,layer):
        for params in layer.parameters():
            params.requires_grad = True


class BiLstmDotOld(Model):

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder = com.Encoder(self.parameter_dict['max_length'], self.parameter_dict['hidden_size']
                                   , self.parameter_dict['number_of_layer'], self.parameter_dict['embedding_dim'],
                                   self.parameter_dict['vocab_size'],
                                   bidirectional=self.parameter_dict['bidirectional'],
                                   vectors=self.parameter_dict['vectors']).cuda(self.device)

    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''

        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data['y_label']
        hidden = self.encoder.init_hidden(ques_batch.shape[0], device)


        optimizer.zero_grad()
        #Encoding all the data
        ques_batch, _ = self.encoder(ques_batch, hidden)
        pos_batch, _ = self.encoder(pos_batch, hidden)
        neg_batch, _ = self.encoder(neg_batch, hidden)
        # Calculating dot score
        pos_scores = torch.sum(ques_batch * pos_batch, -1)
        neg_scores = torch.sum(ques_batch * neg_batch, -1)
        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        optimizer.step()
        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        ques_batch = self.encoder(ques_batch)
        pos_batch = self.encoder(path_batch)

        # Calculating dot score
        score = torch.sum(ques_batch* pos_batch, -1)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()
        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():

            self.encoder.eval()

            hidden = self.encoder.init_hidden(ques.shape[0], device)
            question, _ = self.encoder(ques.long(), hidden)
            paths, _ = self.encoder(paths.long(), hidden)
            score = torch.sum(question[-1] * paths[-1], -1)

            self.encoder.train()

            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.

        :return: [(key, model)]
        """
        return [('encoder', self.encoder)]


class BiLstmDot(Model):

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder = com.NotSuchABetterEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            max_length = self.parameter_dict['max_length'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            mode = 'LSTM',
            debug = self.debug).to(self.device)

    def train(self, data, optimizer, loss_fn, device):
    #
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''

        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        hidden = self.encoder.init_hidden(ques_batch.shape[0],self.device)
        _, ques_batch_encoded, _, _ = self.encoder(tu.trim(ques_batch), hidden)
        _, pos_batch_encoded, _, _ = self.encoder(tu.trim(pos_batch), hidden)
        _, neg_batch_encoded, _, _  = self.encoder(tu.trim(neg_batch), hidden)

        # Calculating dot score
        pos_scores = torch.sum(ques_batch_encoded * pos_batch_encoded, -1)
        neg_scores = torch.sum(ques_batch_encoded * neg_batch_encoded, -1)

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        try:
            loss = loss_fn(pos_scores, neg_scores, y_label)
        except RuntimeError:
            print(pos_scores.shape, neg_scores.shape, y_label.shape,  ques_batch.shape, pos_batch.shape, neg_batch.shape)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.encoder.parameters(), .5)
        optimizer.step()
        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object
            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        hidden = self.encoder.init_hidden(ques_batch.shape[0], self.device)
        _, ques_batch, _, _ = self.encoder(tu.trim(ques_batch), hidden)
        _, pos_batch, _, _ = self.encoder(tu.trim(path_batch), hidden)

        #
        # norm_ques_batch = torch.abs(torch.norm(ques_batch,dim=1,p=1))
        # norm_pos_batch = torch.abs(torch.norm(pos_batch,dim=1,p=1))

        # ques_batch = F.normalize(F.relu(ques_batch),p=1,dim=1)
        # pos_batch = F.normalize(F.relu(pos_batch),p=1,dim=1)
        # ques_batch =(F.normalize(ques_batch,p=1,dim=1)/2) + .5
        # pos_batch =(F.normalize(pos_batch,p=1,dim=1)/2) + .5




        # Calculating dot score
        score = torch.sum(ques_batch * pos_batch, -1)
        # score = score.div(norm_ques_batch*norm_pos_batch).div_(2.0).add_(0.5)
            # print("shape of score is,", score.shape)
            # print("score is , ", score)
            #
            #
            # print("shape of y label is ", y_label.shape)
            # print("value of y label is ", y_label)

        # raise ValueError

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.encoder.parameters(), .5)
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():

            self.encoder.eval()
            hidden = self.encoder.init_hidden(ques.shape[0], self.device)

            _, question, _, _ = self.encoder(tu.trim(ques.long()), hidden)
            _, paths, _, _ = self.encoder(tu.trim(paths.long()), hidden)

            if self.pointwise:
                # question = F.normalize(F.relu(question),p=1,dim=1)
                # paths = F.normalize(F.relu(paths),p=1,dim=1)
                # norm_ques_batch = torch.abs(torch.norm(question, dim=1, p=1))
                # norm_pos_batch = torch.abs(torch.norm(paths, dim=1, p=1))
                score = torch.sum(question * paths, -1)
                # score = score.div(norm_ques_batch * norm_pos_batch).div_(2.0).add_(0.5)
            else:
                score = torch.sum(question * paths, -1)

            self.encoder.train()
            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.

        :return: [(key, model)]
        """
        return [('encoder', self.encoder)]

    def load_from(self, location):
        # Pull the data from disk
        if self.debug: print("loading Bilstmdot model from", location)
        self.encoder.load_state_dict(torch.load(location)['encoder'])
        if self.debug: print("model loaded with weights ,", self.get_parameter_sum())


class BiLstmDense(Model):
    """
        This model replaces the dot product of BiLstmDot with a two layered dense classifier.
        Plus, we only use the last state of the encoder in doing so.
        Like before, we have both pairwise and pointwise versions.
    """

    def __init__(self, _parameter_dict, _word_to_id,  _device, _pointwise=False, _debug=False):
        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id
        self.hiddendim = self.parameter_dict['hidden_size'] * (2 * int(self.parameter_dict['bidirectional']))

        if self.debug:
            print("Init Models")

        self.encoder = com.NotSuchABetterEncoder(max_length=self.parameter_dict['max_length'],
                                                 hidden_dim=self.parameter_dict['hidden_size'],
                                                 number_of_layer=self.parameter_dict['number_of_layer'],
                                                 embedding_dim=self.parameter_dict['embedding_dim'],
                                                 vocab_size=self.parameter_dict['vocab_size'], bidirectional=True,
                                                 dropout=self.parameter_dict['dropout'], mode='LSTM', enable_layer_norm=False,
                                                 vectors=self.parameter_dict['vectors'], debug=self.debug).to(self.device)

        self.dense = com.DenseClf(inputdim=self.hiddendim*2,        # *2 because we have two things concatinated here
                                  hiddendim=self.hiddendim/2,
                                  outputdim=1).to(self.device)

    def train(self, data, optimizer, loss_fn, device):

        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''

        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data[
            'y_label']

        optimizer.zero_grad()
        # Encoding all the data
        hidden = self.encoder.init_hidden(ques_batch.shape[0], self.device)
        _, ques_batch_encoded, _, _ = self.encoder(tu.trim(ques_batch), hidden)
        _, pos_batch_encoded, _, _ = self.encoder(tu.trim(pos_batch), hidden)
        _, neg_batch_encoded, _, _  = self.encoder(tu.trim(neg_batch), hidden)

        # Calculating dot score
        pos_scores = self.dense(torch.cat((ques_batch_encoded, pos_batch_encoded), dim=1))
        neg_scores = self.dense(torch.cat((ques_batch_encoded, neg_batch_encoded), dim=1))

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''

        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.encoder.parameters()+self.dense.parameters(), .5)
        optimizer.step()

        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        hidden = self.encoder.init_hidden(ques_batch.shape[0], self.device)
        _, ques_batch, _, _ = self.encoder(tu.trim(ques_batch), hidden)
        _, pos_batch, _, _ = self.encoder(tu.trim(path_batch), hidden)

        # Calculating dot score
        score = self.dense(torch.cat((ques_batch, pos_batch), dim=1)).squeeze()

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''

        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():

            self.encoder.eval()
            hidden = self.encoder.init_hidden(ques.shape[0], self.device)

            _, question, _, _ = self.encoder(tu.trim(ques.long()), hidden)
            _, paths, _, _ = self.encoder(tu.trim(paths.long()), hidden)
            score = self.dense(torch.cat((question, paths), dim=1)).squeeze()
            self.encoder.train()

            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.

        :return: [(key, model)]
        """
        return [('encoder', self.encoder), ('dense', self.dense)]


class BiLstmDenseDot(Model):
    """
        This model uses the encoder, then condenses the vector into something of a smaller dimension.
        Then uses a regular dot product to compute the final deal.
        Plus, we only use the last state of the encoder in doing so.
        Like before, we have both pairwise and pointwise versions.
    """

    def __init__(self, _parameter_dict, _word_to_id,  _device, _pointwise=False, _debug=False):
        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.word_to_id = _word_to_id
        self.pointwise = _pointwise

        self.hiddendim = self.parameter_dict['hidden_size'] * (2 * int(self.parameter_dict['bidirectional']))

        if self.debug:
            print("Init Models")
        self.encoder = com.NotSuchABetterEncoder(max_length=self.parameter_dict['max_length'],
                                                 hidden_dim=self.parameter_dict['hidden_size'],
                                                 number_of_layer=self.parameter_dict['number_of_layer'],
                                                 embedding_dim=self.parameter_dict['embedding_dim'],
                                                 vocab_size=self.parameter_dict['vocab_size'], bidirectional=True,
                                                 dropout=self.parameter_dict['dropout'], mode='LSTM', enable_layer_norm=False,
                                                 vectors=self.parameter_dict['vectors'], debug=self.debug).to(self.device)

        self.dense = com.DenseClf(inputdim=self.hiddendim,
                                  hiddendim=self.hiddendim/2,
                                  outputdim=self.hiddendim/4).to(self.device)

    def train(self, data, optimizer, loss_fn, device):

        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''

        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data[
            'y_label']

        optimizer.zero_grad()

        # Encoding all the data
        hidden = self.encoder.init_hidden(ques_batch.shape[0], self.device)
        _, ques_batch_encoded, _, _ = self.encoder(tu.trim(ques_batch), hidden)
        _, pos_batch_encoded, _, _ = self.encoder(tu.trim(pos_batch), hidden)
        _, neg_batch_encoded, _, _ = self.encoder(tu.trim(neg_batch), hidden)


        # Pass all encoded stuff through the dense too
        ques_batch = self.dense(ques_batch_encoded)
        pos_batch = self.dense(pos_batch_encoded)
        neg_batch = self.dense(neg_batch_encoded)


        # Calculating dot score
        pos_scores = torch.sum(ques_batch * pos_batch, -1)
        neg_scores = torch.sum(ques_batch * neg_batch, -1)

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''

        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        hidden = self.encoder.init_hidden(ques_batch.shape[0], self.device)
        _, ques_batch, _, _ = self.encoder(tu.trim(ques_batch), hidden)
        _, pos_batch, _, _ = self.encoder(tu.trim(path_batch), hidden)

        # Compress the last state
        ques_batch = self.dense(ques_batch)
        pos_batch = self.dense(pos_batch)

        # Calculating dot score
        score = torch.sum(ques_batch * pos_batch, -1)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''

        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """

        with torch.no_grad():

            self.encoder.eval()

            hidden = self.encoder.init_hidden(ques.shape[0], self.device)

            _, question, _, _ = self.encoder(tu.trim(ques.long()), hidden)
            _, paths, _, _ = self.encoder(tu.trim(paths.long()), hidden)

            # Dense
            question = self.dense(question)
            paths = self.dense(paths)

            score = torch.sum(question * paths, -1)

            self.encoder.train()

            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.
https://arxiv.org/pdf/1606.01933.pdf
        :return: [(key, model)]
        """
        return [('encoder', self.encoder), ('dense', self.dense)]


class CNNDot(Model):

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder = com.CNN(_vectors=self.parameter_dict['vectors'], _vocab_size=self.parameter_dict['vocab_size'] ,
                           _embedding_dim = self.parameter_dict['embedding_dim'] , _output_dim = self.parameter_dict['output_dim'],_debug=self.debug).to(self.device)

    def train(self, data, optimizer, loss_fn, device):
    #
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''

        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data['y_label']

        optimizer.zero_grad()
        #Encoding all the data

        ques_batch_encoded = self.encoder(ques_batch)
        pos_batch_encoded = self.encoder(pos_batch)
        neg_batch_encoded = self.encoder(neg_batch)



        #Calculating dot score
        pos_scores = torch.sum(ques_batch_encoded * pos_batch_encoded, -1)
        neg_scores = torch.sum(ques_batch_encoded * neg_batch_encoded, -1)
        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        try:
            loss = loss_fn(pos_scores, neg_scores, y_label)
        except RuntimeError:
            print(pos_scores.shape, neg_scores.shape, y_label.shape,  ques_batch.shape, pos_batch.shape, neg_batch.shape)
        loss.backward()
        optimizer.step()
        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object
            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        ques_batch = self.encoder(ques_batch)
        pos_batch = self.encoder(path_batch)

        # Calculating dot score
        score = torch.sum(ques_batch * pos_batch, -1)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():

            self.encoder.eval()

            question = self.encoder(ques.long())
            paths = self.encoder(paths.long())

            if self.pointwise:
                # question = F.normalize(F.relu(question),p=1,dim=1)
                # paths = F.normalize(F.relu(paths),p=1,dim=1)
                # norm_ques_batch = torch.abs(torch.norm(question, dim=1, p=1))
                # norm_pos_batch = torch.abs(torch.norm(paths, dim=1, p=1))
                score = torch.sum(question * paths, -1)
                # score = score.div(norm_ques_batch * norm_pos_batch).div_(2.0).add_(0.5)
            else:
                score = torch.sum(question * paths, -1)

            self.encoder.train()
            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.

        :return: [(key, model)]
        """
        return [('encoder', self.encoder)]

    # def load_from(self, location):
    #     # Pull the data from disk
    #     if self.debug: print("loading Bilstmdot model from", location)
    #     self.encoder.load_state_dict(torch.load(location)['encoder'])
    #     if self.debug: print("model loaded with weights ,", self.get_parameter_sum())


class DecomposableAttention(Model):
    """
        Implementation of https://arxiv.org/pdf/1606.01933.pdf.
        Uses an encoder and AttendCompareAggregate class in components
    """
    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id
        self.hiddendim = self.parameter_dict['hidden_size'] * (1+ int(self.parameter_dict['bidirectional']))

        if self.debug:
            print("Init Models")

        # self.encoder = FlatEncoder(embdim=self.parameter_dict['embedding_dim'],
        #                            dims=[self.parameter_dict['hidden_size']],
        #                            word_dic=self.word_to_id,
        #                            bidir=True,dropout_rec=self.parameter_dict['dropout_rec'],
        #                            dropout_in=self.parameter_dict['dropout_in']).to(self.device)

        # self.encoder = com.Encoder(self.parameter_dict['max_length'], self.parameter_dict['hidden_size']
        #                            , self.parameter_dict['number_of_layer'], self.parameter_dict['embedding_dim'],
        #                            self.parameter_dict['vocab_size'],
        #                            bidirectional=self.parameter_dict['bidirectional'],
        #                            vectors=self.parameter_dict['vectors']).to(self.device)

        self.encoder = com.NotSuchABetterEncoder(max_length = self.parameter_dict['max_length'],
                                                 hidden_dim = self.parameter_dict['hidden_size'],
                                                 number_of_layer = self.parameter_dict['number_of_layer'],
                                                 embedding_dim = self.parameter_dict['embedding_dim'],
                                                 vocab_size = self.parameter_dict['vocab_size'], bidirectional = True,
                                                 dropout = self.parameter_dict['dropout'], mode = 'LSTM', enable_layer_norm = False,
                                                 vectors = self.parameter_dict['vectors'], debug = self.debug).to(self.device)

        self.scorer = com.BetterAttendCompareAggregate(inputdim=self.hiddendim, debug=self.debug).to(self.device)

    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data[
            'y_label']

        hidden = self.encoder.init_hidden(ques_batch.shape[0], device)

        optimizer.zero_grad()
        # Encoding all the data
        ques_batch_encoded, _, _, ques_mask = self.encoder(tu.trim(ques_batch),hidden)
        pos_batch_encoded, _, _, pos_mask = self.encoder(tu.trim(pos_batch), hidden)
        neg_batch_encoded, _, _, neg_mask = self.encoder(tu.trim(neg_batch), hidden)

        # Now, we get a pos and a neg score.
        pos_scores = self.scorer(ques_batch_encoded, pos_batch_encoded, ques_mask, pos_mask)
        neg_scores = self.scorer(ques_batch_encoded, neg_batch_encoded, ques_mask, neg_mask)

        '''
                    If `y == 1` then it assumed the first input should be ranked higher
                    (have a larger value) than the second input, and vice-versa for `y == -1`
        '''

        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        optimizer.step()
        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object
            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        hidden = self.encoder.init_hidden(ques_batch.shape[0], device)

        optimizer.zero_grad()

        # Encoding all the data
        ques_batch, _, _, ques_mask = self.encoder(tu.trim(ques_batch), hidden)
        path_batch, _, _, path_mask = self.encoder(tu.trim(path_batch), hidden)

        # Calculating dot score
        score = self.scorer(ques_batch, path_batch, ques_mask, path_mask).squeeze()

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''

        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():
            self.encoder.eval()
            hidden = self.encoder.init_hidden(ques.shape[0], device)

            question, _, _, question_mask = self.encoder(tu.trim(ques.long()),hidden)
            paths, _, _, paths_mask = self.encoder(tu.trim(paths.long()), hidden)
            score = self.scorer(question, paths, question_mask, paths_mask)

            self.encoder.train()
            return score.squeeze()

    def prepare_save(self):
        return [('encoder', self.encoder), ('scorer', self.scorer)]


class RelDetection(Model):

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id
        self.hiddendim = self.parameter_dict['hidden_size'] * (1+ int(self.parameter_dict['bidirectional']))

        if self.debug:
            print("Init Models")

        self.encoder = com.HRBiLSTM(hidden_dim=_parameter_dict['hidden_size'],
                                    embedding_dim=_parameter_dict['embedding_dim'],
                                    dropout=_parameter_dict['dropout'],
                                    vocab_size=_parameter_dict['vocab_size'],
                                    vectors=_parameter_dict['vectors'],
                                    debug=self.debug,
                                    max_length=_parameter_dict['max_length']).to(self.device)

    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        ques_batch, pos_batch, pos_rel1_batch, pos_rel2_batch, neg_batch, neg_rel1_batch, neg_rel2_batch, y_label = \
            data['ques_batch'], data['pos_batch'], data['pos_rel1_batch'], data['pos_rel2_batch'], \
            data['neg_batch'], data['neg_rel1_batch'], data['neg_rel2_batch'], data['y_label']

        optimizer.zero_grad()

        # Instantiate hidden states
        _hp = self.encoder.init_hidden(ques_batch.shape[0], device=device)
        _hn = self.encoder.init_hidden(ques_batch.shape[0], device=device)

        # Encoding all the data
        pos_scores = self.encoder(ques=ques_batch,
                                  path_word=pos_batch,
                                  path_rel_1=pos_rel1_batch,
                                  path_rel_2=pos_rel2_batch,
                                  _h=_hp)

        neg_scores = self.encoder(ques=ques_batch,
                                  path_word=neg_batch,
                                  path_rel_1=neg_rel1_batch,
                                  path_rel_2=neg_rel2_batch,
                                  _h=_hn)

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''

        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.encoder.parameters(), .5)
        optimizer.step()

        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        ques_batch, path_batch, path_rel1_batch, path_rel2_batch, y_label = \
            data['ques_batch'], data['path_batch'], data['path_rel1_batch'], data['path_rel2_batch'], data['y_label']

        optimizer.zero_grad()

        # Instantiate hidden states
        _h = self.encoder.init_hidden(ques_batch.shape[0], device=device)

        # Encoding all the data

        score = self.encoder(ques=ques_batch,
                             path_word=path_batch,
                             path_rel_1=path_rel1_batch,
                             path_rel_2=path_rel2_batch,
                             _h=_h)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.encoder.parameters(), .5)
        optimizer.step()

        return loss

    def predict(self, ques, paths, paths_rel1,paths_rel2, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():
            self.encoder.eval()
            _h = self.encoder.init_hidden(ques.shape[0], device=device)
            paths_rel1 = tu.no_one_left_behind(paths_rel1)
            paths_rel2 = tu.no_one_left_behind(paths_rel2)
            score = self.encoder(ques=ques,
                                 path_word=paths,
                                 path_rel_1=paths_rel1,
                                 path_rel_2=paths_rel2,
                                 _h=_h).squeeze()
            self.encoder.train()
            return score

    def prepare_save(self):
        return [('model',self.encoder)]


class QelosSlotPointerModel(Model):

    """
        Eating Denis's shit
    """
    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder_q = com.QelosSlotPtrQuestionEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=True,
            mode = 'LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug = self.debug).to(self.device)


        self.encoder_p = com.QelosSlotPtrChainEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            bidirectional=self.parameter_dict['bidirectional'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=False,
            mode = 'LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug = self.debug).to(self.device)


    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        ques_batch, pos_1_batch, pos_2_batch, neg_1_batch, neg_2_batch, y_label = \
            data['ques_batch'], data['pos_rel1_batch'], data['pos_rel2_batch'], \
            data['neg_rel1_batch'], data['neg_rel2_batch'], data['y_label']

        optimizer.zero_grad()

        # Have to manually check if the 2nd paths holds anything in this batch.
        # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
        pos_2_batch = tu.no_one_left_behind(pos_2_batch)
        neg_2_batch = tu.no_one_left_behind(neg_2_batch)


        # assert torch.mean((torch.sum(pos_2_batch, dim=-1) != 0).float()) == 1
        # assert torch.mean((torch.sum(pos_1_batch, dim=-1) != 0).float()) == 1

        # Encoding all the data
        ques_encoded,_ = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(pos_1_batch), tu.trim(pos_2_batch))
        neg_encoded = self.encoder_p(tu.trim(neg_1_batch), tu.trim(neg_2_batch))

        # Pass them to the comparison module
        pos_scores = torch.sum(ques_encoded * pos_encoded, dim=-1)
        neg_scores = torch.sum(ques_encoded * neg_encoded, dim=-1)

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        # torch.nn.utils.clip_grad_norm_(self.encoder_q.parameters(), .5)
        # torch.nn.utils.clip_grad_norm_(self.encoder_p.parameters(), .5)
        optimizer.step()

        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        ques_batch, path_1_batch, path_2_batch, y_label = \
            data['ques_batch'], data['path_rel1_batch'], data['path_rel2_batch'], data['y_label']


        optimizer.zero_grad()
        path_2_batch = tu.no_one_left_behind(path_2_batch)

        # Encoding all the data
        ques_encoded,_ = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(path_1_batch), tu.trim(path_2_batch))

        score = torch.sum(ques_encoded * pos_encoded, dim=-1)

        '''
            Binary Cross Entropy loss function. 
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        # torch.nn.utils.clip_grad_norm_(self.encoder_q.parameters(), .5)
        # torch.nn.utils.clip_grad_norm_(self.encoder_p.parameters(), .5)
        optimizer.step()

        return loss

    def predict(self, ques, paths, paths_rel1,paths_rel2, device,attention_value=False):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():
            self.encoder_q.eval()
            self.encoder_p.eval()

            # Have to manually check if the 2nd paths holds anything in this batch.
            # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
            paths_rel2 = tu.no_one_left_behind(paths_rel2)

            # Encoding all the data
            ques_encoded,attention_score = self.encoder_q(tu.trim(ques))
            path_encoded = self.encoder_p(tu.trim(paths_rel1), tu.trim(paths_rel2))

            # Pass them to the comparison module
            score = torch.sum(ques_encoded * path_encoded, dim=-1)

            self.encoder_q.train()
            self.encoder_p.train()
            if attention_value:
                return score,attention_score
            else:
                return score

    def prepare_save(self):
        return [('encoder_q', self.encoder_q), ('encoder_p', self.encoder_p)]


class SlotPointerModel(Model):

    """
        EAT MY SAHIT DENIS
    """
    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder_q = com.NotSuchABetterEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            bidirectional=self.parameter_dict['bidirectional'],
            hidden_dim=self.parameter_dict['embedding_dim']/2,
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            residual=True,
            mode = 'LSTM',
            debug = self.debug).to(self.device)

        self.encoder_p = com.NotSuchABetterEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            bidirectional=self.parameter_dict['bidirectional'],
            hidden_dim=self.parameter_dict['embedding_dim']/2,
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            residual=True,
            mode = 'LSTM',
            debug = self.debug).to(self.device)

        self.comparer = com.SlotPointer(
            embedding_dim=self.parameter_dict['embedding_dim'],
            max_len_ques=self.parameter_dict['max_length'],
            hidden_dim=self.parameter_dict['embedding_dim']/2,
            max_len_path=self.parameter_dict['relsp_pad'],
            vocab_size=self.parameter_dict['vocab_size'],
            debug=self.debug).to(self.device)

    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        ques_batch, pos_1_batch, pos_2_batch, neg_1_batch, neg_2_batch, y_label = \
            data['ques_batch'], data['pos_rel1_batch'], data['pos_rel2_batch'], \
            data['neg_rel1_batch'], data['neg_rel2_batch'], data['y_label']

        hidden = self.encoder_q.init_hidden(ques_batch.shape[0], device)

        optimizer.zero_grad()

        # Have to manually check if the 2nd paths holds anything in this batch.
        # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
        pos_2_batch = tu.no_one_left_behind(pos_2_batch)
        neg_2_batch = tu.no_one_left_behind(neg_2_batch)

        # Encoding all the data
        ques_batch_encoded, _, _, ques_mask, ques_batch_embedded, _ = self.encoder_q(tu.trim(ques_batch),hidden)
        _, pos_1_encoded, _, pos_1_mask, pos_1_embedded, _ = self.encoder_p(pos_1_batch, hidden)
        _, pos_2_encoded, _, pos_2_mask , pos_2_embedded, _ = self.encoder_p(pos_2_batch, hidden)
        _, neg_1_encoded, _, neg_1_mask , neg_1_embedded, _ = self.encoder_p(neg_1_batch, hidden)
        _, neg_2_encoded, _, neg_2_mask , neg_2_embedded, _ = self.encoder_p(neg_2_batch, hidden)

        # Pass them to the comparison module
        pos_scores = self.comparer(ques_enc=ques_batch_encoded,
                                   ques_emb=ques_batch_embedded,
                                   ques_mask=ques_mask,
                                   path_1_enc=pos_1_encoded,
                                   path_1_emb=pos_1_embedded,
                                   path_1_mask = pos_1_mask,
                                   path_2_enc=pos_2_encoded,
                                   path_2_emb=pos_2_embedded,
                                   path_2_mask = pos_2_mask)

        # Pass them to the comparison module
        neg_scores = self.comparer(ques_enc=ques_batch_encoded,
                                   ques_emb=ques_batch_embedded,
                                   ques_mask=ques_mask,
                                   path_1_enc=neg_1_encoded,
                                   path_1_emb=neg_1_embedded,
                                   path_1_mask = neg_1_mask,
                                   path_2_enc=neg_2_encoded,
                                   path_2_emb=neg_2_embedded,
                                   path_2_mask = neg_2_mask)

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''

        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def _train_pointwise(self, data, optimizer, loss_fn, device):
        ques_batch, path_1_batch, path_2_batch, y_label = \
            data['ques_batch'], data['path_rel1_batch'], data['path_rel2_batch'], data['y_label']

        path_2_batch = tu.no_one_left_behind(path_2_batch)

        hidden = self.encoder_q.init_hidden(ques_batch.shape[0], device)

        optimizer.zero_grad()

        # Encoding all the data
        ques_batch_encoded, _, _, ques_mask, ques_batch_embedded, _ = self.encoder_q(tu.trim(ques_batch), hidden)
        _, pos_1_encoded, _, pos_1_mask, pos_1_embedded, _ = self.encoder_p(path_1_batch, hidden)
        _, pos_2_encoded, _, pos_2_mask, pos_2_embedded, _ = self.encoder_p(path_2_batch, hidden)
        # _, pos_1_encoded, _, _, _, pos_1_embedded = self.encoder_p(path_1_batch, hidden)
        # _, pos_2_encoded, _, _, _, pos_2_embedded = self.encoder_p(path_2_batch, hidden)

        # score = self.comparer(ques_enc=ques_batch_encoded,
        #                            ques_emb=ques_batch_embedded,
        #                            ques_mask=ques_mask,
        #                            path_1_enc=pos_1_encoded,
        #                            path_1_emb=pos_1_embedded,
        #                            path_2_enc=pos_2_encoded,
        #                            path_2_emb=pos_2_embedded)

        score = self.comparer(ques_enc=ques_batch_encoded,
                                   ques_emb=ques_batch_embedded,
                                   ques_mask=ques_mask,
                                   path_1_enc=pos_1_encoded,
                                   path_1_emb=pos_1_embedded,
                                   path_1_mask=pos_1_mask,
                                   path_2_enc=pos_2_encoded,
                                   path_2_emb=pos_2_embedded,
                                   path_2_mask=pos_2_mask)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, paths_rel1,paths_rel2, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():
            self.encoder_q.eval()
            self.encoder_p.eval()
            self.comparer.eval()
            hidden = self.encoder_q.init_hidden(ques.shape[0], device=device)

            paths_rel2 = tu.no_one_left_behind(paths_rel2)

            # Encoding all the data
            ques_batch_encoded, _, _, ques_mask, ques_batch_embedded, _ = self.encoder_q(tu.trim(ques), hidden)
            _, pos_1_encoded, _, pos_1_mask,  pos_1_embedded, _ = self.encoder_p(paths_rel1, hidden)
            _, pos_2_encoded, _, pos_2_mask,  pos_2_embedded, _ = self.encoder_p(paths_rel2, hidden)

            score = self.comparer(ques_enc=ques_batch_encoded,
                                  ques_emb=ques_batch_embedded,
                                  ques_mask=ques_mask,
                                  path_1_enc=pos_1_encoded,
                                  path_1_emb=pos_1_embedded,
                                  path_1_mask=pos_1_mask,
                                  path_2_enc=pos_2_encoded,
                                  path_2_emb=pos_2_embedded,
                                  path_2_mask=pos_2_mask).squeeze()

            self.encoder_q.train()
            self.encoder_p.train()
            self.comparer.train()
            return score

    def prepare_save(self):
        return [('model', self.encoder_q)]


class BiLstmDot_skip(Model):
    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")



        self.encoder = com.QelosFlatEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            max_length = self.parameter_dict['max_length'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            mode = 'LSTM',
            debug = self.debug,
            device = self.device,
            residual=True).to(self.device)

    def train(self, data, optimizer, loss_fn, device):
    #
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''

        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data['y_label']

        optimizer.zero_grad()
        #Encoding all the data

        ques_batch_encoded = self.encoder(tu.trim(ques_batch))
        pos_batch_encoded = self.encoder(tu.trim(pos_batch))
        neg_batch_encoded = self.encoder(tu.trim(neg_batch))



        #Calculating dot score
        pos_scores = torch.sum(ques_batch_encoded * pos_batch_encoded, -1)
        neg_scores = torch.sum(ques_batch_encoded * neg_batch_encoded, -1)
        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        try:
            loss = loss_fn(pos_scores, neg_scores, y_label)
        except RuntimeError:
            print(pos_scores.shape, neg_scores.shape, y_label.shape,  ques_batch.shape, pos_batch.shape, neg_batch.shape)
        loss.backward()
        optimizer.step()
        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object
            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        ques_batch = self.encoder(tu.trim(ques_batch))
        pos_batch = self.encoder(tu.trim(path_batch))

        # Calculating dot score
        score = torch.sum(ques_batch * pos_batch, -1)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():

            self.encoder.eval()

            question = self.encoder(tu.trim(ques.long()))
            paths = self.encoder(tu.trim(paths.long()))

            if self.pointwise:
                # question = F.normalize(F.relu(question),p=1,dim=1)
                # paths = F.normalize(F.relu(paths),p=1,dim=1)
                # norm_ques_batch = torch.abs(torch.norm(question, dim=1, p=1))
                # norm_pos_batch = torch.abs(torch.norm(paths, dim=1, p=1))
                score = torch.sum(question * paths, -1)
                # score = score.div(norm_ques_batch * norm_pos_batch).div_(2.0).add_(0.5)
            else:
                score = torch.sum(question * paths, -1)

            self.encoder.train()
            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.

        :return: [(key, model)]
        """
        return [('encoder', self.encoder)]

    def load_from(self, location):
        # Pull the data from disk
        if self.debug: print("loading Bilstmdot model from", location)
        self.encoder.load_state_dict(torch.load(location)['encoder'])
        if self.debug: print("model loaded with weights ,", self.get_parameter_sum())


class BiLstmDot_multiencoder(Model):

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")



        self.encoder_q = com.NotSuchABetterEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            max_length = self.parameter_dict['max_length'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            mode = 'LSTM',
            residual=False,
            debug = self.debug).to(self.device)

        self.encoder_p = com.NotSuchABetterEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            max_length=self.parameter_dict['max_length'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            mode='LSTM',
            residual=False,
            debug=self.debug).to(self.device)

    def train(self, data, optimizer, loss_fn, device):
    #
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''

        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data['y_label']

        optimizer.zero_grad()
        #Encoding all the data

        hidden = self.encoder_q.init_hidden(ques_batch.shape[0],self.device)
        _, ques_batch_encoded, _, _ = self.encoder_q(tu.trim(ques_batch), hidden)
        _, pos_batch_encoded, _, _ = self.encoder_p(tu.trim(pos_batch), hidden)
        _, neg_batch_encoded, _, _  = self.encoder_p(tu.trim(neg_batch), hidden)



        #Calculating dot score
        pos_scores = torch.sum(ques_batch_encoded * pos_batch_encoded, -1)
        neg_scores = torch.sum(ques_batch_encoded * neg_batch_encoded, -1)
        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        try:
            loss = loss_fn(pos_scores, neg_scores, y_label)
        except RuntimeError:
            print(pos_scores.shape, neg_scores.shape, y_label.shape,  ques_batch.shape, pos_batch.shape, neg_batch.shape)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(list(self.encoder_q.parameters()) + list(self.encoder_p.parameters()), .5)
        optimizer.step()
        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object
            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        hidden = self.encoder_q.init_hidden(ques_batch.shape[0], self.device)
        _, ques_batch, _, _ = self.encoder_q(tu.trim(ques_batch), hidden)
        _, pos_batch, _, _ = self.encoder_p(tu.trim(path_batch), hidden)

        #
        # norm_ques_batch = torch.abs(torch.norm(ques_batch,dim=1,p=1))
        # norm_pos_batch = torch.abs(torch.norm(pos_batch,dim=1,p=1))

        # ques_batch = F.normalize(F.relu(ques_batch),p=1,dim=1)
        # pos_batch = F.normalize(F.relu(pos_batch),p=1,dim=1)
        # ques_batch =(F.normalize(ques_batch,p=1,dim=1)/2) + .5
        # pos_batch =(F.normalize(pos_batch,p=1,dim=1)/2) + .5




        # Calculating dot score
        score = torch.sum(ques_batch * pos_batch, -1)
        # score = score.div(norm_ques_batch*norm_pos_batch).div_(2.0).add_(0.5)
            # print("shape of score is,", score.shape)
            # print("score is , ", score)
            #
            #
            # print("shape of y label is ", y_label.shape)
            # print("value of y label is ", y_label)

        # raise ValueError

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(list(self.encoder_q.parameters()) + list(self.encoder_p.parameters()), .5)
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():

            self.encoder_q.eval()
            self.encoder_p.eval()
            hidden = self.encoder_q.init_hidden(ques.shape[0], self.device)

            _, question, _, _ = self.encoder_q(tu.trim(ques.long()), hidden)
            _, paths, _, _ = self.encoder_p(tu.trim(paths.long()), hidden)

            if self.pointwise:
                # question = F.normalize(F.relu(question),p=1,dim=1)
                # paths = F.normalize(F.relu(paths),p=1,dim=1)
                # norm_ques_batch = torch.abs(torch.norm(question, dim=1, p=1))
                # norm_pos_batch = torch.abs(torch.norm(paths, dim=1, p=1))
                score = torch.sum(question * paths, -1)
                # score = score.div(norm_ques_batch * norm_pos_batch).div_(2.0).add_(0.5)
            else:
                score = torch.sum(question * paths, -1)

            self.encoder_q.train()
            self.encoder_p.train()
            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.

        :return: [(key, model)]
        """
        return [('encoder_q', self.encoder_q),('encoder_p', self.encoder_p)]

    def load_from(self, location):
        # Pull the data from disk
        if self.debug: print("loading Bilstmdot model from", location)
        self.encoder.load_state_dict(torch.load(location)['encoder'])
        if self.debug: print("model loaded with weights ,", self.get_parameter_sum())


class QelosSlotPointerModel_common_encoder(QelosSlotPointerModel):

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):
        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder_q = com.QelosSlotPtrQuestionEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=True,
            mode='LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug=self.debug).to(self.device)

        enc = self.encoder_q.return_encoder()

        self.encoder_p = com.QelosSlotPtrChainEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            bidirectional=self.parameter_dict['bidirectional'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=True,
            mode='LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug=self.debug,
            encoder=enc).to(self.device)



class BiLstmDot_ulmfit(Model):

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        # Load the pre-trained model
        pretrained_weights = torch.load('./ulmfit/wt103/fwd_wt103_enc.h5', map_location= lambda storage, loc: storage)
        new_vectors = self.parameter_dict['vectors']
        pretrained_weights['encoder.weight'] = T(new_vectors)
        pretrained_weights.pop('encoder_with_dropout.embed.weight')

        self.encoder = com.awdencoder(rnn_type='LSTM',
                                       ntoken=self.parameter_dict['vectors'].shape[0],
                                       ninp=400,
                                       nhid=1150,
                                       nlayers=3,
                                       dropout=0.1,
                                       dropouth=0.5,
                                       dropouti=0.5,
                                       dropoute=0.5,
                                       wdrop=0,
                                       tie_weights=True)
        self.encoder.encoder.padding_idx = 0

        key_mapping = {
            'encoder.weight': 'encoder.weight',
            'rnns.0.module.weight_ih_l0': 'rnns.0.weight_ih_l0',
            'rnns.0.module.bias_ih_l0': 'rnns.0.bias_ih_l0',
            'rnns.0.module.bias_hh_l0': 'rnns.0.bias_hh_l0',
            'rnns.0.module.weight_hh_l0_raw': 'rnns.0.weight_hh_l0',
            'rnns.1.module.weight_ih_l0': 'rnns.1.weight_ih_l0',
            'rnns.1.module.bias_ih_l0': 'rnns.1.bias_ih_l0',
            'rnns.1.module.bias_hh_l0': 'rnns.1.bias_hh_l0',
            'rnns.1.module.weight_hh_l0_raw': 'rnns.1.weight_hh_l0',
            'rnns.2.module.weight_ih_l0': 'rnns.2.weight_ih_l0',
            'rnns.2.module.bias_ih_l0': 'rnns.2.bias_ih_l0',
            'rnns.2.module.bias_hh_l0': 'rnns.2.bias_hh_l0',
            'rnns.2.module.weight_hh_l0_raw': 'rnns.2.weight_hh_l0',
        }

        for k, v in key_mapping.items():
            pretrained_weights[v] = pretrained_weights.pop(k)

        self.encoder = self.encoder.to(self.device)
        self.encoder.load_state_dict(pretrained_weights)

        self.encoder.reset()




    def train(self, data, optimizer, loss_fn, device):
    #
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, pos paths, neg paths and dummy y labels}
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object

            returns loss
        '''
        self.encoder.train()
        # Unpacking the data and model from args
        ques_batch, pos_batch, neg_batch, y_label = data['ques_batch'], data['pos_batch'], data['neg_batch'], data[
            'y_label']

        optimizer.zero_grad()
        # Encoding all the data

        h = self.encoder.init_hidden(ques_batch.shape[0])
        op_q = self.encoder(tu.trim(ques_batch).transpose(1, 0), h)[1][-1][0].squeeze()
        op_p = self.encoder(tu.trim(pos_batch).transpose(1, 0), h)[1][-1][0].squeeze()
        op_n = self.encoder(tu.trim(neg_batch).transpose(1, 0), h)[1][-1][0].squeeze()


        # Calculating dot score
        pos_scores = torch.sum(op_q * op_p, -1)
        neg_scores = torch.sum(op_q * op_n, -1)

        #         if True:
        #             print("ques_batch shape is ", ques_batch.shape)
        #             print("pos_batch shape is ", pos_batch.shape)
        #             print("neg_batch shape is ", neg_batch.shape)
        #             print("transposed ques bathc is ", ques_batch.transpose(1,0).shape)
        #             for o in op_p[1]:
        #                 print("o shape is ", o.shape)
        #             print("encoded pos batch shape is ", op_p[1][-1][-1].shape)

        #             print("pos_score is", pos_scores.shape)
        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        #         raise ValueError
        try:
            loss = loss_fn(pos_scores, neg_scores, y_label)
        except RuntimeError:
            traceback.print_exc()
            print(pos_scores.shape, neg_scores.shape, y_label.shape, ques_batch.shape, pos_batch.shape, neg_batch.shape)

        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.encoder.parameters(), .5)
        optimizer.step()
        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        '''
            Given data, passes it through model, inited in constructor, returns loss and updates the weight
            :params data: {batch of question, paths and y labels}
            :params models list of [models]
            :params optimizer: torch.optim object
            :params loss fn: torch.nn loss object
            :params device: torch.device object
            returrns loss
        '''
        # Unpacking the data and model from args
        ques_batch, path_batch, y_label = data['ques_batch'], data['path_batch'], data['y_label']

        optimizer.zero_grad()

        # Encoding all the data
        h = self.encoder.init_hidden(ques_batch.shape[0])
        ques_batch = self.encoder(tu.trim(ques_batch).transpose(1,0),h)[1][-1][0].squeeze()
        pos_batch = self.encoder(tu.trim(path_batch).transpose(1,0),h)[1][-1][0].squeeze()



        # Calculating dot score
        score = torch.sum(ques_batch * pos_batch, -1)


        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.encoder.parameters(), .5)
        optimizer.step()

        return loss

    def predict(self, ques, paths, device):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():

            self.encoder.eval()
            # Encoding all the data
            h = self.encoder.init_hidden(ques.shape[0])
            question = self.encoder(tu.trim(ques).transpose(1,0),h)[1][-1][0].squeeze()
            paths = self.encoder(tu.trim(paths).transpose(1,0),h)[1][-1][0].squeeze()

            if self.pointwise:
                # question = F.normalize(F.relu(question),p=1,dim=1)
                # paths = F.normalize(F.relu(paths),p=1,dim=1)
                # norm_ques_batch = torch.abs(torch.norm(question, dim=1, p=1))
                # norm_pos_batch = torch.abs(torch.norm(paths, dim=1, p=1))
                score = torch.sum(question * paths, -1)
                # score = score.div(norm_ques_batch * norm_pos_batch).div_(2.0).add_(0.5)
            else:
                score = torch.sum(question * paths, -1)

            self.encoder.train()
            return score

    def prepare_save(self):
        """

            This function is called when someone wants to save the underlying models.
            Returns a tuple of key:model pairs which is to be interpreted within save model.

        :return: [(key, model)]
        """
        return [('encoder', self.encoder)]

    def load_from(self, location):
        # Pull the data from disk
        if self.debug: print("loading Bilstmdot model from", location)
        self.encoder.load_state_dict(torch.load(location)['encoder'])
        if self.debug: print("model loaded with weights ,", self.get_parameter_sum())




class QelosSlotPointerModelOrthogonal(Model):

    """
        Eating Denis's shit
    """
    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder_q = com.QelosSlotPtrQuestionEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=True,
            mode = 'LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug = self.debug).to(self.device)


        self.encoder_p = com.QelosSlotPtrChainEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            bidirectional=self.parameter_dict['bidirectional'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=False,
            mode = 'LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug = self.debug).to(self.device)


    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        ques_batch, pos_1_batch, pos_2_batch, neg_1_batch, neg_2_batch, y_label = \
            data['ques_batch'], data['pos_rel1_batch'], data['pos_rel2_batch'], \
            data['neg_rel1_batch'], data['neg_rel2_batch'], data['y_label']

        optimizer.zero_grad()

        # Have to manually check if the 2nd paths holds anything in this batch.
        # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
        pos_2_batch = tu.no_one_left_behind(pos_2_batch)
        neg_2_batch = tu.no_one_left_behind(neg_2_batch)


        # assert torch.mean((torch.sum(pos_2_batch, dim=-1) != 0).float()) == 1
        # assert torch.mean((torch.sum(pos_1_batch, dim=-1) != 0).float()) == 1

        # Encoding all the data
        ques_encoded,attention = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(pos_1_batch), tu.trim(pos_2_batch))
        neg_encoded = self.encoder_p(tu.trim(neg_1_batch), tu.trim(neg_2_batch))

        # Pass them to the comparison module
        pos_scores = torch.sum(ques_encoded * pos_encoded, dim=-1)
        neg_scores = torch.sum(ques_encoded * neg_encoded, dim=-1)
        attention_scores_a12 = torch.sum(attention[:, :, 0] * attention[:, :, 1], dim=1)/\
                               (torch.norm(attention[:, :, 1])*torch.norm(attention[:, :, 0]))
        attention_scores_a11 = torch.sum(attention[:, :, 0] * attention[:, :, 0], dim=1)
        attention_scores_a22 = torch.sum(attention[:, :, 1] * attention[:, :, 1], dim=1)
        # attention_scores = torch.sum(torch.min(attention[:, :, 0, :] , attention[:, :, 1, :]))
        # attention_scores = torch.sum(attention[:,:,0,:] * attention[:,:,0,:],dim=1) \
        #                    + torch.sum(attention[:,:,1,:] * attention[:,:,1,:],dim=1) \
        #                    + torch.sum(attention[:, :, 1, :] * attention[:, :, 0, :], dim=1)**2

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        loss = loss_fn(pos_scores, neg_scores, y_label)
        # print("shape of loss before adding attention", loss.shape)
        # print("shape of attention_scores before adding attention", attention_scores.shape)
        # loss = loss + 2*torch.mean(attention_scores_a12,dim=0) - torch.mean(attention_scores_a22,dim=0) - torch.mean(attention_scores_a11,dim=0)
        # print(attention_scores_a12)
        # print(attention_scores_a12.shape)
        loss = loss + 0.3*(torch.mean(attention_scores_a12,dim=0))
        # print("shape of loss after adding attention", loss.shape)
        loss.backward()
        optimizer.step()

        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        ques_batch, path_1_batch, path_2_batch, y_label = \
            data['ques_batch'], data['path_rel1_batch'], data['path_rel2_batch'], data['y_label']

        path_2_batch = tu.no_one_left_behind(path_2_batch)

        optimizer.zero_grad()

        # Encoding all the data
        ques_encoded,_ = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(path_1_batch), tu.trim(path_2_batch))

        score = torch.sum(ques_encoded * pos_encoded, dim=-1)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, paths_rel1,paths_rel2, device,attention_value=False):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():
            self.encoder_q.eval()
            self.encoder_p.eval()

            # Have to manually check if the 2nd paths holds anything in this batch.
            # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
            paths_rel2 = tu.no_one_left_behind(paths_rel2)

            # Encoding all the data
            ques_encoded,attention_score = self.encoder_q(tu.trim(ques))
            path_encoded = self.encoder_p(tu.trim(paths_rel1), tu.trim(paths_rel2))

            # Pass them to the comparison module
            score = torch.sum(ques_encoded * path_encoded, dim=-1)

            self.encoder_q.train()
            self.encoder_p.train()
            if attention_value:
                return score,attention_score
            else:
                return score

    def prepare_save(self):
        return [('encoder_q', self.encoder_q), ('encoder_p', self.encoder_p)]


class QelosSlotPointerModelOrthogonalEntity(Model):

    """
        Eating Denis's shit
    """
    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder_q = com.QelosSlotPtrQuestionEncoderEntity(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=True,
            mode = 'LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug = self.debug).to(self.device)


        self.encoder_p = com.QelosSlotPtrChainEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            bidirectional=self.parameter_dict['bidirectional'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=False,
            mode = 'LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug = self.debug).to(self.device)


    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        ques_batch, pos_1_batch, pos_2_batch, neg_1_batch, neg_2_batch, y_label = \
            data['ques_batch'], data['pos_rel1_batch'], data['pos_rel2_batch'], \
            data['neg_rel1_batch'], data['neg_rel2_batch'], data['y_label']

        optimizer.zero_grad()

        # Have to manually check if the 2nd paths holds anything in this batch.
        # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
        pos_2_batch = tu.no_one_left_behind(pos_2_batch)
        neg_2_batch = tu.no_one_left_behind(neg_2_batch)

        # assert torch.mean((torch.sum(pos_2_batch, dim=-1) != 0).float()) == 1
        # assert torch.mean((torch.sum(pos_1_batch, dim=-1) != 0).float()) == 1

        # Encoding all the data
        ques_encoded, attention = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(pos_1_batch), tu.trim(pos_2_batch))
        neg_encoded = self.encoder_p(tu.trim(neg_1_batch), tu.trim(neg_2_batch))

        # Pass them to the comparison module
        pos_scores = torch.sum(ques_encoded * pos_encoded, dim=-1)
        neg_scores = torch.sum(ques_encoded * neg_encoded, dim=-1)

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''

        attention_scores_a12 = (torch.sum(attention[:, :, 0] * attention[:, :, 1], dim=1)) / (
                    torch.norm(attention[:, :, 1]) * torch.norm(attention[:, :, 0]))
        attention_scores_a11 = torch.sum(attention[:, :, 0] * attention[:, :, 0], dim=1)
        attention_scores_a22 = torch.sum(attention[:, :, 1] * attention[:, :, 1], dim=1)
        #         ascore = 0.5*torch.mean(attention_scores_a12,dim=0) + 0.5*torch.mean(torch.ones_like(attention_scores_a11) - attention_scores_a11,dim=0) + 0.5*torch.mean(torch.ones_like(attention_scores_a11) - attention_scores_a22,dim=0)
        ascore = 0.5 * (torch.mean(attention_scores_a12, dim=0))
        #         ascore = 0
        loss = loss_fn(pos_scores, neg_scores, y_label) + ascore
        loss.backward()
        optimizer.step()

        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        ques_batch, path_1_batch, path_2_batch, y_label = \
            data['ques_batch'], data['path_rel1_batch'], data['path_rel2_batch'], data['y_label']

        path_2_batch = tu.no_one_left_behind(path_2_batch)

        optimizer.zero_grad()

        # Encoding all the data
        ques_encoded,_ = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(path_1_batch), tu.trim(path_2_batch))

        score = torch.sum(ques_encoded * pos_encoded, dim=-1)

        '''
            Binary Cross Entropy loss function. @TODO: Check if we can give it 1/0 labels.
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, paths_rel1,paths_rel2, device,attention_value=False):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():
            self.encoder_q.eval()
            self.encoder_p.eval()

            # Have to manually check if the 2nd paths holds anything in this batch.
            # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
            paths_rel2 = tu.no_one_left_behind(paths_rel2)

            # Encoding all the data
            ques_encoded,attention_score = self.encoder_q(tu.trim(ques))
            path_encoded = self.encoder_p(tu.trim(paths_rel1), tu.trim(paths_rel2))

            # Pass them to the comparison module
            score = torch.sum(ques_encoded * path_encoded, dim=-1)

            self.encoder_q.train()
            self.encoder_p.train()
            if attention_value:
                return score,attention_score
            else:
                return score

    def prepare_save(self):
        return [('encoder_q', self.encoder_q), ('encoder_p', self.encoder_p)]


class ULMFITQelosSlotPointerModel(Model):
    """
        Eating Denis's shit
    """

    def __init__(self, _parameter_dict, _word_to_id, _device, _pointwise=False, _debug=False):

        self.debug = _debug
        self.parameter_dict = _parameter_dict
        self.device = _device
        self.pointwise = _pointwise
        self.word_to_id = _word_to_id

        if self.debug:
            print("Init Models")

        self.encoder_q = com.ULMFITQelosSlotPtrQuestionEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            bidirectional=self.parameter_dict['bidirectional'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=True,
            mode='LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug=self.debug).to(self.device)

        enc = self.encoder_q.return_encoder()

        self.encoder_p = com.ULMFITQelosSlotPtrChainEncoder(
            number_of_layer=self.parameter_dict['number_of_layer'],
            embedding_dim=self.parameter_dict['embedding_dim'],
            bidirectional=self.parameter_dict['bidirectional'],
            hidden_dim=self.parameter_dict['hidden_size'],
            vocab_size=self.parameter_dict['vocab_size'],
            max_length=self.parameter_dict['max_length'],
            dropout=self.parameter_dict['dropout'],
            vectors=self.parameter_dict['vectors'],
            enable_layer_norm=False,
            device=_device,
            residual=False,
            mode='LSTM',
            dropout_in=self.parameter_dict['dropout_in'],
            dropout_rec=self.parameter_dict['dropout_rec'],
            debug=self.debug,
            encoder=enc).to(self.device)

    @property
    def layers(self):
        return torch.nn.ModuleList(
            #             [l for l in self.encoder_p.layers] +
            [l for l in self.encoder_q.layers]
        )

    def train(self, data, optimizer, loss_fn, device):
        if self.pointwise:
            return self._train_pointwise_(data, optimizer, loss_fn, device)
        else:
            return self._train_pairwise_(data, optimizer, loss_fn, device)

    def _train_pairwise_(self, data, optimizer, loss_fn, device):
        ques_batch, pos_1_batch, pos_2_batch, neg_1_batch, neg_2_batch, y_label = \
            data['ques_batch'], data['pos_rel1_batch'], data['pos_rel2_batch'], \
            data['neg_rel1_batch'], data['neg_rel2_batch'], data['y_label']

        optimizer.zero_grad()

        # Have to manually check if the 2nd paths holds anything in this batch.
        # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
        pos_2_batch = tu.no_one_left_behind(pos_2_batch)
        neg_2_batch = tu.no_one_left_behind(neg_2_batch)

        # Encoding all the data
        #         if True:
        #             print(f"Shape of ques trimmed is: {tu.trim(ques_batch).shape}")
        #             print(f"Shape of pos1 trimmed is: {tu.trim(pos_1_batch).shape}")
        #             print(f"Shape of pos2 trimmed is: {tu.trim(pos_2_batch).shape}")
        ques_encoded, _ = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(pos_1_batch), tu.trim(pos_2_batch))
        neg_encoded = self.encoder_p(tu.trim(neg_1_batch), tu.trim(neg_2_batch))

        # Pass them to the comparison module
        pos_scores = torch.sum(ques_encoded * pos_encoded, dim=-1)
        neg_scores = torch.sum(ques_encoded * neg_encoded, dim=-1)

        '''
            If `y == 1` then it assumed the first input should be ranked higher
            (have a larger value) than the second input, and vice-versa for `y == -1`
        '''
        loss = loss_fn(pos_scores, neg_scores, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def _train_pointwise_(self, data, optimizer, loss_fn, device):
        ques_batch, path_1_batch, path_2_batch, y_label = \
            data['ques_batch'], data['path_rel1_batch'], data['path_rel2_batch'], data['y_label']

        optimizer.zero_grad()
        path_2_batch = tu.no_one_left_behind(path_2_batch)

        # Encoding all the data
        ques_encoded, _ = self.encoder_q(tu.trim(ques_batch))
        pos_encoded = self.encoder_p(tu.trim(path_1_batch), tu.trim(path_2_batch))

        score = torch.sum(ques_encoded * pos_encoded, dim=-1)

        '''
            Binary Cross Entropy loss function. 
        '''
        loss = loss_fn(score, y_label)
        loss.backward()
        optimizer.step()

        return loss

    def predict(self, ques, paths, paths_rel1, paths_rel2, device, attention_value=False):
        """
            Same code works for both pairwise or pointwise
        """
        with torch.no_grad():
            self.encoder_q.eval()
            self.encoder_p.eval()

            # Have to manually check if the 2nd paths holds anything in this batch.
            # If not, we have to pad everything up with zeros, or even call a limited part of the comparison module.
            paths_rel2 = tu.no_one_left_behind(paths_rel2)

            # Encoding all the data
            ques_encoded, attention_score = self.encoder_q(tu.trim(ques))
            path_encoded = self.encoder_p(tu.trim(paths_rel1), tu.trim(paths_rel2))

            # Pass them to the comparison module
            score = torch.sum(ques_encoded * path_encoded, dim=-1)

            self.encoder_q.train()
            self.encoder_p.train()
            if attention_value:
                return score, attention_score
            else:
                return score

    def prepare_save(self):
        return [('encoder_q', self.encoder_q), ('encoder_p', self.encoder_p)]

