"""
    The file with different models for corechain ranking.
    bidirectional_dot

"""

from __future__ import absolute_import
import os
import sys
import json
import warnings
import numpy as np
from sklearn.utils import shuffle


import keras.backend.tensorflow_backend as K
from keras.models import Model
from keras.layers import Input, Lambda

import prepare_transfer_learning
import network as n

# Macros
DEBUG = True
CHECK_VALIDATION_ACC_PERIOD = 10
LCQUAD_BIRNN_MODEL = 'model_14'


# Better warning formatting. Ignore.
def better_warning(message, category, filename, lineno, file=None, line=None):
    return ' %s:%s: %s:%s\n' % (filename, lineno, category.__name__, message)


def bidirectional_dot_sigmoidloss(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train = 10,
                                  _neg_paths_per_epoch_test = 1000, _index=None, _transfer_model_path=None):
    """
        Data Time!
    """
    # Pull the data up from disk
    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j + 10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]
    if counter > 0:
        print(counter)
        warnings.warn("critical condition needs to be entered")
    np.random.seed(0)  # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index:
        split_point = index + 1
    else:
        split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]

    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions) * neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions) * (neg_paths_per_epoch_test + 1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 128

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        encode = n._simple_BiRNNEncoding(max_length, embedding_dims, nr_hidden, 0.5)

        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode(x_ques_embedded)
            path_encoded = encode(x_path_embedded)

            # holographic_score = holographic_forward(Lambda(lambda x: cross_correlation(x)) ([ques_encoded, path_encoded]))
            dot_score = n.dot([ques_encoded, path_encoded], axes=-1)
            # l1_score = Lambda(lambda x: K.abs(x[0]-x[1]))([ques_encoded, path_encoded])

            # return final_forward(concatenate([holographic_score, dot_score, l1_score], axis=-1))
            return dot_score

        pos_score = getScore(x_ques, x_pos_path)
        neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: 1.0 - K.sigmoid(x[0] - x[1]))([pos_score, neg_score])

        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path],
                      outputs=[output])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER,
                      loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                     max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                         max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=CHECK_VALIDATION_ACC_PERIOD)

        model.fit_generator(training_generator,
                            epochs=n.EPOCHS,
                            workers=3,
                            use_multiprocessing=True,
                            callbacks=[checkpointer])
        # callbacks=[EarlyStopping(monitor='val_loss', min_delta=0, patience=0, verbose=0, mode='auto') ])

        print("Precision (hits@1) = ",
              n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


def bidirectional_dot(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train = 10,
                      _neg_paths_per_epoch_test = 1000, _index=None, _transfer_model_path=None) :
    """
        Data Time!
    """
    # Pull the data up from disk
    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j + 10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]
    if counter > 0:
        print(counter)
        warnings.warn("critical condition needs to be entered")
    np.random.seed(0)  # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index: split_point = lambda x: _index+1
    else: split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]

    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions) * neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions) * (neg_paths_per_epoch_test + 1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        # max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 128

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        encode = n._simple_BiRNNEncoding(max_length, embedding_dims, nr_hidden, 0.4, _name="encoder")

        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode(x_ques_embedded)
            path_encoded = encode(x_path_embedded)

            # holographic_score = holographic_forward(Lambda(lambda x: cross_correlation(x)) ([ques_encoded, path_encoded]))
            dot_score = n.dot([ques_encoded, path_encoded], axes=-1)
            # l1_score = Lambda(lambda x: K.abs(x[0]-x[1]))([ques_encoded, path_encoded])

            # return final_forward(concatenate([holographic_score, dot_score, l1_score], axis=-1))
            return dot_score

        pos_score = getScore(x_ques, x_pos_path)
        neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: K.maximum(0., 1.0 - x[0] + x[1]))([pos_score, neg_score])

        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path],
                      outputs=[output])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER,
                      loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                     max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                         max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=CHECK_VALIDATION_ACC_PERIOD)

        model.fit_generator(training_generator,
                            epochs=n.EPOCHS,
                            workers=3,
                            use_multiprocessing=True,
                            callbacks=[checkpointer])
        # callbacks=[EarlyStopping(monitor='val_loss', min_delta=0, patience=0, verbose=0, mode='auto') ])

        print("Precision (hits@1) = ",
              n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


def two_bidirectional_dot(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train = 10,
                      _neg_paths_per_epoch_test = 1000, _index=None, _transfer_model_path=None):
    """
        A bi-lstm encodes the input.
        Another bi-lstm encodes the op
        siamese setup
        dot
    """
    # Pull the data up from disk
    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j + 10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]
    if counter > 0:
        print(counter)
        warnings.warn("Critical condition needs to be entered")
    np.random.seed(0)  # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index: split_point = lambda x: _index+1
    else: split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]

    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions) * neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions) * (neg_paths_per_epoch_test + 1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 128

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        encode_one = n._double_BiRNNEncoding(max_length, embedding_dims, nr_hidden, 0.4, True, _name="double_encoder")
        # encode_two = n._BiRNNEncoding(max_length, nr_hidden*2, nr_hidden/2, 0.4)

        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode_one(x_ques_embedded)
            path_encoded = encode_one(x_path_embedded)

            dot_score = n.dot([ques_encoded, path_encoded], axes=-1)

            return dot_score

        pos_score = getScore(x_ques, x_pos_path)
        neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: K.maximum(0., 1.0 - x[0] + x[1]))([pos_score, neg_score])

        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path],
                      outputs=[output])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER,
                      loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                     max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                         max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=CHECK_VALIDATION_ACC_PERIOD)

        model.fit_generator(training_generator,
                            epochs=n.EPOCHS,
                            workers=3,
                            use_multiprocessing=True,
                            callbacks=[checkpointer])
        # callbacks=[EarlyStopping(monitor='val_loss', min_delta=0, patience=0, verbose=0, mode='auto') ])

        print("Precision (hits@1) = ",
              n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


def bidirectional_dense(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train = 10,
                      _neg_paths_per_epoch_test = 1000, _index=None, _transfer_model_path=None):
    """
        Data Time!
    """
    # Pull the data up from disk
    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j + 10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]
    if counter > 0:
        print(counter)
        warnings.warn("critical condition needs to be entered")
    np.random.seed(0)  # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index:
        split_point = index + 1
    else:
        split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]

    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions) * neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions) * (neg_paths_per_epoch_test + 1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 64

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        # encode = n._BiRNNEncoding(max_length, embedding_dims, nr_hidden, 0.5)
        encode = n._simple_BiRNNEncoding(max_length, embedding_dims, nr_hidden, 0.5, return_sequences=False)
        dense = n._simpleDense(max_length, nr_hidden)

        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode(x_ques_embedded)
            path_encoded = encode(x_path_embedded)

            ques_dense = dense(ques_encoded)
            path_dense = dense(path_encoded)

            dot_score = n.dot([ques_dense, path_dense],axes = -1)
            return dot_score

        pos_score = getScore(x_ques, x_pos_path)
        neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: K.maximum(0., 1.0 - x[0] + x[1]))([pos_score, neg_score])

        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path],
                      outputs=[output])

        print(model.summary())
        # if DEBUG: raw_input("Check the summary before going ahead!")

        model.compile(optimizer=n.OPTIMIZER,
                      loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                     max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                         max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=10)

        model.fit_generator(training_generator,
                            epochs=n.EPOCHS,
                            workers=3,
                            use_multiprocessing=True,
                            callbacks=[checkpointer])
        # callbacks=[EarlyStopping(monitor='val_loss', min_delta=0, patience=0, verbose=0, mode='auto') ])

        print("Precision (hits@1) = ",
              n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


def parikh(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train=10,
           _neg_paths_per_epoch_test=1000, _index=None, _transfer_model_path=None):

    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j+10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]

    # Shuffle these matrices together @TODO this!
    np.random.seed(0) # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index:
        split_point = index + 1
    else:
        split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]
    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions)*neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions)*(neg_paths_per_epoch_test+1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 128

        # holographic_forward = Dense(1, activation='sigmoid')
        # final_forward = Dense(1, activation='sigmoid')

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        encode = n._BiRNNEncoding(max_length, embedding_dims,  nr_hidden, 0.5)
        # encode = n._simple_BiRNNEncoding(max_length, embedding_dims,  nr_hidden, 0.5)
        # encode = LSTM(max_length)(encode)
        attend = n._Attention(max_length, nr_hidden, dropout=0.6, L2=0.01)
        align = n._SoftAlignment(max_length, nr_hidden)
        compare = n._Comparison(max_length, nr_hidden, dropout=0.6, L2=0.01)
        entail = n._Entailment(nr_hidden, 1, dropout=0.4, L2=0.01)
        dense = n._simpleDense(max_length*2,nr_hidden*2)
        # encode_step_2 = n._simple_CNNEncoding(max_length*2, embedding_dims, nr_hidden, 0.5)


        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode(x_ques_embedded)
            path_encoded = encode(x_path_embedded)

            # ques_encoded_last_output = ques_encoded[:,-1,:]
            ques_encoded_last_output = Lambda(lambda x: x[:,-1,:])(ques_encoded)
            # path_encoded_last_output = path_encoded[:,-1,:]
            path_encoded_last_output = Lambda(lambda x: x[:,-1,:])(path_encoded)

            # holographic_score = holographic_forward(Lambda(lambda x: cross_correlation(x)) ([ques_encoded, path_encoded]))
            # dot_score = dot([ques_encoded, path_encoded], axes=-1)
            # l1_score = Lambda(lambda x: K.abs(x[0]-x[1]))([ques_encoded, path_encoded])

            # return final_forward(concatenate([holographic_score, dot_score, l1_score], axis=-1))
            # return dot_score

            #
            attention = attend(ques_encoded, path_encoded)

            align_ques = align(path_encoded, attention)
            align_path = align(ques_encoded, attention, transpose=True)

            feats_ques = compare(ques_encoded, align_ques)
            feats_path = compare(path_encoded, align_path)


			# poop
            ques_concat = n.concatenate(
                [feats_ques,ques_encoded_last_output], axis=-1
            )

            # ques_concat = n.merge(
            #     [feats_ques, ques_encoded_last_output]
            # )
			#
            path_concat = n.concatenate(
                [feats_path,path_encoded_last_output], axis=-1
            )

            # path_concat = n.merge(
            #     [feats_path, path_encoded_last_output]
            # )

            dense_ques = dense(ques_concat)
            dense_path = dense(path_concat)

            # new_ques = encode_step_2(feats_ques)
            # new_path = encode_step_2(feats_path)
            dot_score = n.dot([dense_ques, dense_path], axes=-1, normalize=True)
            # dot_score = n.dot([feats_ques, feats_path], axes=-1, normalize=True)
            return dot_score

        pos_score = getScore(x_ques, x_pos_path)
        neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: K.maximum(0., 1.0 - x[0] + x[1]))([pos_score, neg_score])


        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path], outputs=[output])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER, loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                  max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                  max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=CHECK_VALIDATION_ACC_PERIOD)

        model.fit_generator(training_generator, epochs=n.EPOCHS, workers=3, use_multiprocessing=True, callbacks=[checkpointer])

        print("Precision (hits@1) = ",
              n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


def maheshwari(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train=10,
               _neg_paths_per_epoch_test=1000, _index=None, _transfer_model_path=None):

    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j+10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]

    # Shuffle these matrices together @TODO this!
    np.random.seed(0) # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index:
        split_point = index + 1
    else:
        split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]
    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions)*neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions)*(neg_paths_per_epoch_test+1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 128

        # holographic_forward = Dense(1, activation='sigmoid')
        # final_forward = Dense(1, activation='sigmoid')

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        encode = n._BiRNNEncoding(max_length, embedding_dims,  nr_hidden, 0.5)
        # encode = n._simple_BiRNNEncoding(max_length, embedding_dims,  nr_hidden, 0.5)
        # encode = LSTM(max_length)(encode)
        attend = n._Attention(max_length, nr_hidden, dropout=0.6, L2=0.01)
        align = n._SoftAlignment(max_length, nr_hidden)
        compare = n._Comparison(max_length, nr_hidden, dropout=0.6, L2=0.01)
        entail = n._Entailment(nr_hidden, 1, dropout=0.4, L2=0.01)

        x_ques_embedded = embed(x_ques)
        x_pos_path_embedded = embed(x_pos_path)
        x_neg_path_embedded = embed(x_neg_path)

        ques_encoded = encode(x_ques_embedded)
        pos_path_encoded = encode(x_pos_path_embedded)
        neg_path_encoded = encode(x_neg_path_embedded)

        def getScore(path_pos, path_neg):

            attention = attend(path_pos, path_neg)

            align_pos = align(path_pos, attention)
            align_neg = align(path_neg, attention, transpose=True)

            feats_pos = compare(path_pos, align_pos)
            feats_neg = compare(path_neg, align_neg)

            return feats_pos, feats_neg

        pos_path_attended, neg_path_attended = getScore(pos_path_encoded, neg_path_encoded)

        pos_score = n.dot([ques_encoded, pos_path_attended], axes=-1)
        neg_score = n.dot([ques_encoded, neg_path_attended], axes=-1)

        # neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: K.maximum(0., 1.0 - x[0] + x[1]))([pos_score, neg_score])

        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path], outputs=[output])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER, loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                  max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                  max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, train_questions, train_pos_paths, train_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=CHECK_VALIDATION_ACC_PERIOD)

        model.fit_generator(training_generator, epochs=n.EPOCHS, workers=3, use_multiprocessing=True, callbacks=[checkpointer])

        print("Precision (hits@1) = ",
              n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


def parikh_dot(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train=10,
               _neg_paths_per_epoch_test = 1000, _index=None, _transfer_model_path=None):
    # Pull the data up from disk
    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j + 10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]
    if counter > 0:
        print(counter)
        warnings.warn("critical condition needs to be entered")
    np.random.seed(0)  # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index:
        split_point = index + 1
    else:
        split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]

    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions) * neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions) * (neg_paths_per_epoch_test + 1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):

        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 64

        # holographic_forward = Dense(1, activation='sigmoid')
        # final_forward = Dense(1, activation='sigmoid')

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        encode = n._BiRNNEncoding(max_length, embedding_dims, nr_hidden, 0.5)
        encode_simple = n._simple_BiRNNEncoding(max_length, embedding_dims, nr_hidden/2, 0.4)
        # encode = n._simple_BiRNNEncoding(max_length, embedding_dims,  nr_hidden, 0.5)
        # encode = LSTM(max_length)(encode)
        attend = n._Attention(max_length, nr_hidden, dropout=0.6, L2=0.01)
        align = n._SoftAlignment(max_length, nr_hidden)
        compare = n._Comparison(max_length, nr_hidden, dropout=0.6, L2=0.01)
        entail = n._Entailment(nr_hidden, 1, dropout=0.4, L2=0.01)
        dense = n._simpleDense(max_length , int(nr_hidden/2))

        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode(x_ques_embedded)
            path_encoded = encode(x_path_embedded)

            ques_encoded_dot = encode_simple(x_ques_embedded)
            path_encoded_dot = encode_simple(x_path_embedded)

            # ques_encoded_last_output = ques_encoded[:,-1,:]
            # ques_encoded_last_output = Lambda(lambda x: x[:,-1,:])(ques_encoded)
            # # path_encoded_last_output = path_encoded[:,-1,:]
            # path_encoded_last_output = Lambda(lambda x: x[:,-1,:])(path_encoded)

            # holographic_score = holographic_forward(Lambda(lambda x: cross_correlation(x)) ([ques_encoded, path_encoded]))
            # dot_score = dot([ques_encoded, path_encoded], axes=-1)
            # l1_score = Lambda(lambda x: K.abs(x[0]-x[1]))([ques_encoded, path_encoded])

            # return final_forward(concatenate([holographic_score, dot_score, l1_score], axis=-1))
            # return dot_score

            #
            attention = attend(ques_encoded, path_encoded)

            align_ques = align(path_encoded, attention)
            align_path = align(ques_encoded, attention, transpose=True)

            feats_ques = compare(ques_encoded, align_ques)
            feats_path = compare(path_encoded, align_path)


            #
            # ques_concat = n.concatenate(
            #     [feats_ques,ques_encoded_dot], axis=-1
            # )

            # print ques_concat.shape

            ques_concat = n.merge(
                [feats_ques, ques_encoded_dot]
            )
            #
            # path_concat = n.concatenate(
            #     [feats_path,path_encoded_dot], axis=-1
            # )
			#
            # print path_concat.shape

            path_concat = n.merge(
                [feats_path, path_encoded_dot]
            )

            # dense_ques = dense(ques_concat)
            # dense_path = dense(path_concat)

            # new_ques = encode_step_2(feats_ques)
            # new_path = encode_step_2(feats_path)
            dot_score = n.dot([ques_concat, path_concat], axes=-1, normalize=True)
            # dot_score = n.dot([feats_ques, feats_path], axes=-1, normalize=True)
            return dot_score

        pos_score = getScore(x_ques, x_pos_path)
        neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: K.maximum(0., 1.0 - x[0] + x[1]))([pos_score, neg_score])


        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path], outputs=[output])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER, loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                  max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                  max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=CHECK_VALIDATION_ACC_PERIOD)

        model.fit_generator(training_generator, epochs=n.EPOCHS, workers=3, use_multiprocessing=True, callbacks=[checkpointer])

        print("Precision (hits@1) = ",
              n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


def cnn_dot(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train = 10,
                      _neg_paths_per_epoch_test = 1000, _index=None, _transfer_model_path=None):
    """
        Data Time!
    """
    # Pull the data up from disk
    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    counter = 0
    for i in range(0, len(pos_paths)):
        temp = -1
        for j in range(0, len(neg_paths[i])):
            if np.array_equal(pos_paths[i], neg_paths[i][j]):
                if j == 0:
                    neg_paths[i][j] = neg_paths[i][j + 10]
                else:
                    neg_paths[i][j] = neg_paths[i][0]
    if counter > 0:
        print(counter)
        warnings.warn("critical condition needs to be entered")
    np.random.seed(0)  # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index:
        split_point = index + 1
    else:
        split_point = lambda x: int(len(x) * .80)

    def train_split(x):
        return x[:split_point(x)]

    def test_split(x):
        return x[split_point(x):]

    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions) * neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions) * (neg_paths_per_epoch_test + 1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        neg_paths_per_epoch_train = 10
        neg_paths_per_epoch_test = 1000
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_pos_path = Input(shape=(max_length,), dtype='int32', name='x_pos_path')
        x_neg_path = Input(shape=(max_length,), dtype='int32', name='x_neg_path')

        embedding_dims = vectors.shape[1]
        nr_hidden = 128

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.2)
        encode = n._simple_CNNEncoding(max_length, embedding_dims, nr_hidden, 0.5)

        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode(x_ques_embedded)
            path_encoded = encode(x_path_embedded)

            # holographic_score = holographic_forward(Lambda(lambda x: cross_correlation(x)) ([ques_encoded, path_encoded]))
            dot_score = n.dot([ques_encoded, path_encoded], axes=-1)
            # l1_score = Lambda(lambda x: K.abs(x[0]-x[1]))([ques_encoded, path_encoded])

            # return final_forward(concatenate([holographic_score, dot_score, l1_score], axis=-1))
            return dot_score

        pos_score = getScore(x_ques, x_pos_path)
        neg_score = getScore(x_ques, x_neg_path)

        loss = Lambda(lambda x: K.maximum(0., 1.0 - x[0] + x[1]))([pos_score, neg_score])

        output = n.concatenate([pos_score, neg_score, loss], axis=-1)

        # Model time!
        model = Model(inputs=[x_ques, x_pos_path, x_neg_path],
                      outputs=[output])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER,
                      loss=n.custom_loss)

        """
            Check if we intend to transfer weights from any other model.
        """
        if _transfer_model_path:
            model = n.load_pretrained_weights(_new_model=model, _trained_model_path=_transfer_model_path)

        # Prepare training data
        training_input = [train_questions, train_pos_paths, train_neg_paths]

        training_generator = n.TrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                     max_length, neg_paths_per_epoch_train, n.BATCH_SIZE)
        validation_generator = n.ValidationDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                         max_length, neg_paths_per_epoch_test, 9999)

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        checkpointer = n.CustomModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=10)

        model.fit_generator(training_generator,
                            epochs=n.EPOCHS,
                            workers=3,
                            use_multiprocessing=True,
                            callbacks=[checkpointer])
        # callbacks=[EarlyStopping(monitor='val_loss', min_delta=0, patience=0, verbose=0, mode='auto') ])

        print("Precision (hits@1) = ",
                n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))

def prepare_validation_data(questions, pos_paths, neg_paths, neg_paths_per_epoch, max_length):
    """
        Function which twists the data in the same way as a training data generator for pointwise does.
    """

    questions = np.reshape(np.repeat(np.reshape(questions,
                                                     (questions.shape[0], 1, questions.shape[1])),
                                          neg_paths_per_epoch, axis=1), (-1, max_length))

    pos_paths = np.reshape(np.repeat(np.reshape(pos_paths,
                                                     (pos_paths.shape[0], 1, pos_paths.shape[1])),
                                          neg_paths_per_epoch, axis=1), (-1, max_length))

    neg_paths_sampled = np.reshape(
        neg_paths[:, np.random.randint(0, 1000, neg_paths_per_epoch), :],
        (-1, max_length))

    questions_shuffled, pos_paths_shuffled, neg_paths_shuffled = \
        shuffle(questions, pos_paths, neg_paths_sampled)

    labels = np.concatenate([np.ones(pos_paths.shape[0]), np.zeros(neg_paths.shape[0])], axis=0)
    questions = np.concatenate([questions, questions], axis=0)
    paths = np.concatenate([pos_paths, neg_paths], axis=0)

    return labels, questions, paths


def pointwise_bidirectional_dot(_gpu, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train = 100,
                      _neg_paths_per_epoch_test = 1000, _index=None, _transfer_model_path=None):
    """
        Data Time!
    """
    # Pull the data up from disk
    gpu = _gpu
    max_length = n.MAX_SEQ_LENGTH

    np.random.seed(0)  # Random train/test splits stay the same between runs

    # Divide the data into diff blocks
    if _index:
        split_point = index + 1
    else:
        split_point = lambda x: int(len(x) * .70)

    def train_split(x):
        return x[:split_point(x)]

    def test_split(x):
        if _index: return x[split_point(x):]
        else: return x[split_point(x):int(.80 * len(x))]


    train_pos_paths = train_split(pos_paths)
    train_neg_paths = train_split(neg_paths)
    train_questions = train_split(questions)

    test_pos_paths = test_split(pos_paths)
    test_neg_paths = test_split(neg_paths)
    test_questions = test_split(questions)

    neg_paths_per_epoch_train = _neg_paths_per_epoch_train
    neg_paths_per_epoch_test = _neg_paths_per_epoch_test
    dummy_y_train = np.zeros(len(train_questions) * neg_paths_per_epoch_train)
    dummy_y_test = np.zeros(len(test_questions) * (neg_paths_per_epoch_test + 1))

    print(train_questions.shape)
    print(train_pos_paths.shape)
    print(train_neg_paths.shape)

    print(test_questions.shape)
    print(test_pos_paths.shape)
    print(test_neg_paths.shape)

    with K.tf.device('/gpu:' + gpu):
        K.set_session(K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=True)))
        """
            Model Time!
        """
        max_length = train_questions.shape[1]
        # Define input to the models
        x_ques = Input(shape=(max_length,), dtype='int32', name='x_ques')
        x_path = Input(shape=(max_length,), dtype='int32', name='x_path')
        # y = Input(shape=(1,), dtype='int32', name='y')

        embedding_dims = vectors.shape[1]
        nr_hidden = 128

        embed = n._StaticEmbedding(vectors, max_length, embedding_dims, dropout=0.3)
        encode = n._simple_BiRNNEncoding(max_length, embedding_dims, nr_hidden, 0.5, _name="encoder")

        def getScore(ques, path):
            x_ques_embedded = embed(ques)
            x_path_embedded = embed(path)

            ques_encoded = encode(x_ques_embedded)
            path_encoded = encode(x_path_embedded)

            dot_score = n.dot([ques_encoded, path_encoded], axes=-1)

            return dot_score

        dotscore = getScore(x_ques, x_path)

        dotscore = Lambda(lambda x: K.sigmoid(x))(dotscore)
        # dotscore = K.sigmoid(dotscore)

        # Model time!
        model = Model(inputs=[x_ques, x_path],
                      outputs=[dotscore])

        print(model.summary())

        model.compile(optimizer=n.OPTIMIZER,
                      loss=n.LOSS)


        # model.fit(x=[train_questions, train_paths],y=train_labels, epochs = 10, verbose=1)

        # # Prepare training data
        training_generator = n.PointWiseTrainingDataGenerator(train_questions, train_pos_paths, train_neg_paths,
                                                              max_length, _neg_paths_per_epoch_train, n.BATCH_SIZE)

        # if DEBUG:
        #     print(train_questions.shape, train_paths.shape, train_labels.shape)
        #     raw_input("Check and go ahead")

        # smart_save_model(model)
        json_desc, dir = n.get_smart_save_path(model)
        model_save_path = os.path.join(dir, 'model.h5')

        # checkpoint = n.ModelCheckpoint(model_save_path,
        #                                monitor='val_metric',
        #                                verbose=1,
        #                                save_best_only=True,
        #                                mode='max',
        #                                period=CHECK_VALIDATION_ACC_PERIOD)
        #
        # model.fit_generator(training_generator,
        #                     epochs=n.EPOCHS,
        #                     workers=3,
        #                     use_multiprocessing=True)

        # test_labels, test_questions, test_paths = prepare_validation_data(test_questions, test_pos_paths, test_neg_paths, neg_paths_per_epoch_test, max_length)

        checkpointer = n.CustomPointWiseModelCheckpoint(model_save_path, test_questions, test_pos_paths, test_neg_paths,
                                               monitor='val_metric',
                                               verbose=1,
                                               save_best_only=True,
                                               mode='max',
                                               period=CHECK_VALIDATION_ACC_PERIOD)

        model.fit_generator(training_generator,
                            epochs=n.EPOCHS,
                            workers=3,
                            use_multiprocessing=True,
                            callbacks=[checkpointer])
        # callbacks=[EarlyStopping(monitor='val_loss', min_delta=0, patience=0, verbose=0, mode='auto') ])

        print("Precision (hits@1) = ",
                n.rank_precision(model, test_questions, test_pos_paths, test_neg_paths, 1000, 10000))


if __name__ == "__main__":

    # Parse arguments
    GPU = sys.argv[1].strip().lower()
    model = sys.argv[2].strip().lower()
    DATASET = sys.argv[3].strip().lower()
    TRANSFER_MODEL_PATH = None

    # See if the args are valid.
    while True:
        try:
            assert GPU in ['0', '1', '2', '3']
            assert model in ['birnn_dot', 'parikh', 'birnn_dense', 'maheshwari', 'birnn_dense_sigmoid','cnn',
                             'parikh_dot','birnn_dot_qald', 'two_birnn_dot', 'pointwise_birnn_dot']
            assert DATASET in ['lcquad', 'qald', 'transfer-a', 'transfer-b', 'transfer-c', 'transfer-proper-qald']
            break
        except AssertionError:
            GPU = raw_input("Did not understand which gpu to use. Please write it again: ")
            model = raw_input("Did not understand which model to use. Please write it again: ")
            DATASET = raw_input("Did not understand which dataset to use. Please write it again: ")

    os.environ['CUDA_VISIBLE_DEVICES'] = GPU
    n.MODEL = 'core_chain/'+model
    n.DATASET = DATASET

    # Load relations and the data
    relations = n.load_relation()

    # @TODO: manage transfer-proper

    if DATASET == 'qald':

        id_train = json.load(open(os.path.join(n.DATASET_SPECIFIC_DATA_DIR % {'dataset':DATASET}, "qald_id_big_data_train.json")))
        id_test = json.load(open(os.path.join(n.DATASET_SPECIFIC_DATA_DIR % {'dataset':DATASET}, "qald_id_big_data_test.json")))

        index = len(id_train) - 1
        FILENAME = 'combined_qald.json'

        json.dump(id_train + id_test, open(os.path.join(n.DATASET_SPECIFIC_DATA_DIR % {'dataset':DATASET}, FILENAME), 'w+'))

    elif DATASET == 'lcquad':
        FILENAME, index = "id_big_data.json", None

    elif DATASET == 'transfer-a':
        FILENAME, index = prepare_transfer_learning.transfer_a()

    elif DATASET == 'transfer-b':
        FILENAME, index = prepare_transfer_learning.transfer_b()

    elif DATASET == 'transfer-c':
        FILENAME, index = prepare_transfer_learning.transfer_c()

    elif DATASET == 'transfer-proper-qald':
        """
            Load model trained on LCQuAD train; and is now going to be trained on QALD train. 
        """
        id_train = json.load(open(os.path.join(n.DATASET_SPECIFIC_DATA_DIR % {'dataset':'qald'}, "qald_id_big_data_train.json")))
        id_test = json.load(open(os.path.join(n.DATASET_SPECIFIC_DATA_DIR % {'dataset':'qald'}, "qald_id_big_data_test.json")))

        index = len(id_train) - 1
        FILENAME = 'combined_qald.json'

        json.dump(id_train + id_test, open(os.path.join(n.DATASET_SPECIFIC_DATA_DIR % {'dataset':DATASET}, FILENAME), 'w+'))
        TRANSFER_MODEL_PATH = os.path.join(n.MODEL_DIR % {'model':n.MODEL, 'dataset':'lcquad'}, LCQUAD_BIRNN_MODEL)

    else:
        warnings.warn("Code never comes here. ")
        FILENAME, index = None, None

    if DEBUG: print("About to choose models")

    # Start training
    if model == 'birnn_dot':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run BiDirectionalRNN with Dot")
        bidirectional_dot(GPU, vectors, questions, pos_paths, neg_paths, 100, 1000, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    elif model == 'two_birnn_dot':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run BiDirectionalRNN with Dot")
        two_bidirectional_dot(GPU, vectors, questions, pos_paths, neg_paths, 100, 1000, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    elif model == 'birnn_dot_sigmoid':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run BiDirectionalRNN with Dot and Sigmoid loss")
        bidirectional_dot_sigmoidloss(GPU, vectors, questions, pos_paths, neg_paths, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    elif model == 'birnn_dense':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run BiDirectionalRNN with Dense")
        bidirectional_dense(GPU, vectors, questions, pos_paths, neg_paths, 10, 1000, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    elif model == 'parikh':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run Parikh et al model")
        parikh(GPU, vectors, questions, pos_paths, neg_paths, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    elif model == 'maheshwari':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run Maheshwari et al model")
        maheshwari(GPU, vectors, questions, pos_paths, neg_paths, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    elif model == 'cnn':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run cnn et al model")
        cnn_dot(GPU, vectors, questions, pos_paths, neg_paths, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    elif model == 'parikh_dot':
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run cnn et al model")
        parikh_dot(GPU, vectors, questions, pos_paths, neg_paths, index, _transfer_model_path=TRANSFER_MODEL_PATH)

    # #######################
    # Pointwise models hereon
    # #######################
    elif model == 'pointwise_birnn_dot':

        # Load relations and the data
        # vectors, questions, paths, labels = n.create_dataset_pointwise("id_big_data.json", n.MAX_SEQ_LENGTH,
        #                                                                relations)
        vectors, questions, pos_paths, neg_paths = n.create_dataset_pairwise(FILENAME, n.MAX_SEQ_LENGTH,
                                                                             relations)

        print("About to run Pointwise BidirectionalRNN with a dot at the helm. God save the queen.")
        pointwise_bidirectional_dot(GPU, vectors, questions, pos_paths, neg_paths, _neg_paths_per_epoch_train=10, _index=index)

    else:
        warnings.warn("Did not choose any model.")
        if DEBUG:
            print("sysargs are: ", GPU, model)


