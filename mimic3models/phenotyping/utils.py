import numpy as np
from mimic3models import nn_utils
from mimic3models import common_utils
import threading
import random


def load_data(reader, discretizer, normalizer, small_part=False, pad=False):
    N = reader.get_number_of_examples()
    if small_part:
        N = 1000
    ret = common_utils.read_chunk(reader, N)
    data = ret["X"]
    ts = ret["t"]
    ys = ret["y"]
    names = ret["name"]
    data = [discretizer.transform(X, end=t)[0] for (X, t) in zip(data, ts)]
    if (normalizer is not None):
        data = [normalizer.transform(X) for X in data]
    ys = np.array(ys, dtype=np.int32)
    if pad:
        whole_data = (nn_utils.pad_zeros(data), ys)
    else:
        whole_data = (data, ys)
    return {"data": whole_data, "ts": ts, "names": names}


class BatchGen(object):

    def __init__(self, reader, discretizer, normalizer, batch_size,
                 small_part, target_repl, shuffle, return_names=False):
        self.batch_size = batch_size
        self.target_repl = target_repl
        self.shuffle = shuffle
        self.return_names = return_names

        ret = load_data(reader, discretizer, normalizer, small_part)
        self.data = ret["data"]
        self.names = ret["names"]
        self.ts = ret["ts"]

        self.steps = (len(self.data[0]) + batch_size - 1) // batch_size
        self.lock = threading.Lock()
        self.generator = self._generator()

    def _generator(self):
        B = self.batch_size
        while True:
            if self.shuffle:
                N = len(self.data[1])
                order = range(N)
                random.shuffle(order)
                tmp_data = [[None] * N, [None] * N]
                tmp_names = [None] * N
                tmp_ts = [None] * N
                for i in range(N):
                    tmp_data[0][i] = self.data[0][order[i]]
                    tmp_data[1][i] = self.data[1][order[i]]
                    tmp_names[i] = self.names[order[i]]
                    tmp_ts[i] = self.ts[order[i]]
                self.data = tmp_data
                self.names = tmp_names
                self.ts = tmp_ts
            else:
                # sort entirely
                X = self.data[0]
                y = self.data[1]
                (X, y, self.names, self.ts) = common_utils.sort_and_shuffle([X, y, self.names, self.ts], B)
                self.data = [X, y]

            self.data[1] = np.array(self.data[1])  # this is important for Keras
            for i in range(0, len(self.data[0]), B):
                x = self.data[0][i:i+B]
                y = self.data[1][i:i+B]
                names = self.names[i:i + B]
                ts = self.ts[i:i + B]

                x = nn_utils.pad_zeros(x)
                y = np.array(y) # (B, 25)

                if self.target_repl:
                    T = x.shape[1]
                    y_rep = np.expand_dims(y, axis=1).repeat(T, axis=1) # (B, T, 25)
                    batch_data = (x, [y, y_rep])
                else:
                    batch_data = (x, y)

                if not self.return_names:
                    yield batch_data
                else:
                    yield {"data": batch_data, "names": names, "ts": ts}

    def __iter__(self):
        return self.generator

    def next(self):
        with self.lock:
            return self.generator.next()

    def __next__(self):
        return self.generator.__next__()
