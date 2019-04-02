#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 17-4-27 下午8:43
# @Author  : Tianyu Liu

import tensorflow as tf
import time
import random
import numpy as np
import encoder


enc = encoder.get_encoder("117M")


class DataLoader(object):
    def __init__(self, data_dir, limits, eos, empty):

        self.train_data_path = [data_dir + '/train/train.summary.id', data_dir + '/train/train.box.val.id',
                                data_dir + '/train/train.box.lab.id', data_dir + '/train/train.box.pos',
                                data_dir + '/train/train.box.rpos', data_dir + '/train/train_summary_field_id.txt',
                                data_dir + '/train/train_summary_pos.txt', data_dir + '/train/train_summary_rpos.txt',
                                data_dir + '/train/train.context']

        self.test_data_path = [data_dir + '/test/test.summary.id', data_dir + '/test/test.box.val.id',
                               data_dir + '/test/test.box.lab.id', data_dir + '/test/test.box.pos',
                               data_dir + '/test/test.box.rpos', data_dir + '/test/test_summary_field_id.txt',
                                data_dir + '/test/test_summary_pos.txt', data_dir + '/test/test_summary_rpos.txt',
                                data_dir + '/test/test.context']

        self.dev_data_path = [data_dir + '/valid/valid.summary.id', data_dir + '/valid/valid.box.val.id',
                              data_dir + '/valid/valid.box.lab.id', data_dir + '/valid/valid.box.pos',
                              data_dir + '/valid/valid.box.rpos', data_dir + '/valid/valid_summary_field_id.txt',
                                data_dir + '/valid/valid_summary_pos.txt', data_dir + '/valid/valid_summary_rpos.txt',
                                data_dir + '/valid/valid.context']


        self.vocab_mask_path = data_dir + '/vocab_local.txt'


        self.limits = limits
        self.man_text_len = 150
        self.man_summary_len = 85
        self.eos = eos
        self.empty = empty
        start_time = time.time()

        print('Reading datasets ...')
        self.train_set = self.load_data(self.train_data_path)
        self.test_set = self.load_data(self.test_data_path)
        self.dev_set = self.load_data(self.dev_data_path)
        print ('Reading datasets comsumes %.3f seconds' % (time.time() - start_time))

        ### load fieldid2word list len 3
        self.fieldid2word = []
        with open(data_dir + "/field2word.txt") as f:
            for line in f:
                fieldid = int(line.strip().split("\t")[0])
                word_list = line.strip().split("\t")[1].split(" ")
                wordid_list = [int(tmp) for tmp in word_list]
                assert len(wordid_list) == 3

                self.fieldid2word.append(wordid_list)

        self.fieldid2word = np.array(self.fieldid2word)

        self.gpt_out_mask = []
        self.target_vocab = []
        with open(self.vocab_mask_path) as f:
            for line in f:
                line_list = line.strip().split()
                for ind, token in enumerate(line_list):
                    self.gpt_out_mask.append(int(token) + 0.0)
                    if token == "1":
                        self.target_vocab.append(ind)

        self.gpt_out_mask[-1] = 1.0
        if self.eos not in self.target_vocab:
            self.target_vocab.append(self.eos)
        if self.empty not in self.target_vocab:
            self.target_vocab.append(self.empty)

        assert len(self.gpt_out_mask) == eos + 1
        print (len(self.gpt_out_mask))
        print (len(self.target_vocab))


    def load_data(self, path):
        summary_path, text_path, field_path, pos_path, rpos_path, dec_field, dec_pos, dec_rpos, cont_path = path
        summaries = open(summary_path, 'r').read().strip().split('\n')
        texts = open(text_path, 'r').read().strip().split('\n')
        fields = open(field_path, 'r').read().strip().split('\n')
        poses = open(pos_path, 'r').read().strip().split('\n')
        rposes = open(rpos_path, 'r').read().strip().split('\n')
        decoder_field = open(dec_field).read().strip().split('\n')
        decoder_pos = open(dec_pos).read().strip().split('\n')
        decoder_rpos = open(dec_rpos).read().strip().split('\n')
        cont_in = open(cont_path).read().strip().split('\n')

        if self.limits > 0:
            summaries = summaries[:self.limits]
            texts = texts[:self.limits]
            fields = fields[:self.limits]
            poses = poses[:self.limits]
            rposes = rposes[:self.limits]
            decoder_field = decoder_field[:self.limits]
            decoder_pos = decoder_pos[:self.limits]
            decoder_rpos = decoder_rpos[:self.limits]
            cont_in = cont_in[:self.limits]

        print (path)
        print (len(summaries))
        print (summaries[0].strip().split(' '))
        summaries = [list(map(int, summary.strip().split(' '))) for summary in summaries]
        texts = [list(map(int, text.strip().split(' '))) for text in texts]
        fields = [list(map(int, field.strip().split(' '))) for field in fields]
        poses = [list(map(int, pos.strip().split(' '))) for pos in poses]
        rposes = [list(map(int, rpos.strip().split(' '))) for rpos in rposes]
        decoder_field = [list(map(int, field.strip().split(' '))) for field in decoder_field]
        decoder_pos = [list(map(int, pos.strip().split(' '))) for pos in decoder_pos]
        decoder_rpos = [list(map(int, rpos.strip().split(' '))) for rpos in decoder_rpos]
        context_in = [list(map(int, cont.strip().split(' '))) for cont in cont_in]


        return summaries, texts, fields, poses, rposes, decoder_field, decoder_pos, decoder_rpos, context_in


    def batch_iter(self, data, batch_size, shuffle, domain):
        summaries, texts, fields, poses, rposes, decoder_field, decoder_pos, decoder_rpos, context_in = data
        data_size = len(summaries)
        num_batches = int(data_size / batch_size) if data_size % batch_size == 0 \
            else int(data_size / batch_size) + 1

        if shuffle:
            shuffle_indices = np.random.permutation(np.arange(data_size))
            summaries = np.array(summaries)[shuffle_indices]
            texts = np.array(texts)[shuffle_indices]
            fields = np.array(fields)[shuffle_indices]
            poses = np.array(poses)[shuffle_indices]
            rposes = np.array(rposes)[shuffle_indices]

            decoder_field = np.array(decoder_field)[shuffle_indices]
            decoder_pos = np.array(decoder_pos)[shuffle_indices]
            decoder_rpos = np.array(decoder_rpos)[shuffle_indices]

            context_in = np.array(context_in)[shuffle_indices]

        for batch_num in range(num_batches):
            start_index = batch_num * batch_size
            end_index = min((batch_num + 1) * batch_size, data_size)

            max_summary_len = max([len(sample) for sample in summaries[start_index:end_index]]) 
            max_text_len = max([len(sample) for sample in texts[start_index:end_index]])
            max_cont_len = max([len(sample) for sample in context_in[start_index:end_index]])


            batch_data = {'enc_in':[], 'enc_fd':[], 'enc_pos':[], 'enc_rpos':[], 'enc_len':[],
                          'dec_in':[], 'dec_len':[], 'dec_out':[], 'oov_map':[], 'dec_field':[],
                          'dec_pos':[], 'dec_rpos':[], 'gpt_context':[], 'context':[], 'enc_in_real':[], 'dec_in_real':[]}

            for summary, text, field, pos, rpos, dec_field, dec_pos, dec_rpos, cont_text in zip(summaries[start_index:end_index], texts[start_index:end_index],
                                            fields[start_index:end_index], poses[start_index:end_index],
                                            rposes[start_index:end_index], 
                                            decoder_field[start_index:end_index], decoder_pos[start_index:end_index],
                                            decoder_rpos[start_index:end_index], context_in[start_index:end_index]):
                summary_len = len(summary)
                text_len = len(text)
                cont_len = len(cont_text)
                pos_len = len(pos)
                rpos_len = len(rpos)
                assert text_len == len(field)
                assert pos_len == len(field)
                assert rpos_len == pos_len

                assert len(dec_field) == len(summary)

                gold = summary + [self.eos] * (max_summary_len - summary_len + 1)
                # context = [self.eos] * (max_summary_len - summary_len) + summary
                summary = summary + [self.eos] * (max_summary_len - summary_len)

                dec_field = dec_field + [self.empty] * (max_summary_len - summary_len)
                dec_pos = dec_pos + [0] * (max_summary_len - summary_len)
                dec_rpos = dec_rpos + [0] * (max_summary_len - summary_len)


                context = [self.empty] * (max_cont_len - cont_len) + cont_text

                text = text + [self.empty] * (max_text_len - text_len)
                field = field + [self.empty] * (max_text_len - text_len)
                pos = pos + [0] * (max_text_len - text_len)
                rpos = rpos + [0] * (max_text_len - text_len)

                
                if max_text_len > self.man_text_len:
                    text = text[:self.man_text_len]

                    context = context[-self.man_text_len:]

                    field = field[:self.man_text_len]
                    pos = pos[:self.man_text_len]
                    rpos = rpos[:self.man_text_len]
                    text_len = min(text_len, self.man_text_len)

                elif max_cont_len > self.man_text_len:
                    context = context[-self.man_text_len:]

                ### OOM
                if max_summary_len > self.man_summary_len:
                    gold = gold[:self.man_summary_len + 1]
                    summary = summary[:self.man_summary_len]

                    # context = context[-self.man_summary_len:]

                    dec_field = dec_field[:self.man_summary_len]
                    dec_pos = dec_pos[:self.man_summary_len]
                    dec_rpos = dec_rpos[:self.man_summary_len]
                    summary_len = min(summary_len, self.man_summary_len)


                if domain == "humans":
                    gpt_context = " Biography :"
                elif domain == "books":
                    gpt_context = " book introduction"
                elif domain == "humans_tune":
                    gpt_context = " Biography :"

                gpt_context, _ = enc.encode(gpt_context)

                # ### check:
                # for token in gold:
                #     if token not in self.target_vocab:
                #         print ("Error!")
                

                ### vocab mask
                text_real = []
                for token in text:
                    if token in self.target_vocab:
                        text_real.append(token)
                    else:
                        text_real.append(self.empty)

                dec_real = []
                for token in summary:
                    if token in self.target_vocab:
                        dec_real.append(token)
                    else:
                        dec_real.append(self.empty)



                batch_data['enc_in'].append(text)
                batch_data['enc_len'].append(text_len)
                batch_data['enc_fd'].append(field)
                batch_data['enc_pos'].append(pos)
                batch_data['enc_rpos'].append(rpos)
                batch_data['dec_in'].append(summary)
                batch_data['dec_len'].append(summary_len)
                batch_data['dec_out'].append(gold)
                batch_data['dec_field'].append(dec_field)
                batch_data['dec_pos'].append(dec_pos)
                batch_data['dec_rpos'].append(dec_rpos)
                batch_data['gpt_context'].append(gpt_context)
                batch_data['context'].append(context)

                batch_data['enc_in_real'].append(text_real)
                batch_data['dec_in_real'].append(dec_real)


            # print (batch_data['enc_in_real'][0])
            # print (batch_data['dec_in_real'][0])
            yield batch_data


