    #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 25 17:44:14 2018

@author: mostafamousavi
last update: 01/29/2021

"""

from __future__ import print_function
from __future__ import division
from keras import backend as K
from keras.models import load_model
from keras.optimizers import Adam
import tensorflow as tf

import numpy as np
import pandas as pd
import math
import csv
import h5py
import time
from os import listdir
import os
import platform
import shutil
from .FEQT_utils import DataGeneratorPrediction, picker, generate_arrays_from_file
from .FEQT_utils import f1, SeqSelfAttention, FeedForward, LayerNormalization
from tqdm import tqdm
from datetime import datetime, timedelta
import multiprocessing
import contextlib
import sys
import warnings
from scipy import signal
from matplotlib.lines import Line2D
warnings.filterwarnings("ignore")
from tensorflow.python.util import deprecation
import tracemalloc
deprecation._PRINT_DEPRECATION_WARNINGS = False
import psutil


try:
    f = open('setup.py')
    for li, l in enumerate(f):
        if li == 8:
            EQT_VERSION = l.split('"')[1]
except Exception:
    EQT_VERSION = "0.1.59"

#tracemalloc.start()
#my_snapshot = None

def karyogram():
    # 값을 계속 사용해야 하므로 전역 변수에 저장한다
    global my_snapshot
    if not my_snapshot:
        # 최초 메모리 상태를 저장한다
        my_snapshot = tracemalloc.take_snapshot()
    else:
        lines = []
        # 현재 메모리 상태를 최초와 비교하여 얼마나 차이가 나는지에 대한 통계를 구한다
        top_stats = tracemalloc.take_snapshot().compare_to(my_snapshot, 'lineno')
        # 메모리 사용량이 많은 순서대로 10개를 구하여 출력한다
        for stat in top_stats[:10]:
            lines.append(str(stat))
        print('\n'.join(lines), flush=True)

def predictor(input_dir=None,
              input_model=None,
              output_dir=None,
              output_probabilities=False,
              detection_threshold=0.3,                
              P_threshold=0.1,
              S_threshold=0.1, 
              number_of_plots=10,
              plot_mode='time',
              estimate_uncertainty=False, 
              number_of_sampling=5,
              loss_weights=[0.03, 0.40, 0.58],
              loss_types=['binary_crossentropy', 'binary_crossentropy', 'binary_crossentropy'],
              input_dimention=(6000, 3),
              normalization_mode='std',
              batch_size=500,
              gpuid=None,
              gpu_limit=None,
              number_of_cpus=5,
              use_multiprocessing=False,
              keepPS=True,
              spLimit=60): 
    
    
    """
    
    Applies a trained model to a windowed waveform to perform both detection and picking at the same time. 


    Parameters
    ----------
    input_dir: str, default=None
        Directory name containing hdf5 and csv files-preprocessed data.
        
    input_model: str, default=None
        Path to a trained model.

    output_dir: str, default=None
        Output directory that will be generated. 
        
    output_probabilities: bool, default=False
        If True, it will output probabilities and estimated uncertainties for each trace into an HDF file.       
         
    detection_threshold : float, default=0.3
        A value in which the detection probabilities above it will be considered as an event.
          
    P_threshold: float, default=0.1
        A value which the P probabilities above it will be considered as P arrival.

    S_threshold: float, default=0.1
        A value which the S probabilities above it will be considered as S arrival.
               
    number_of_plots: float, default=10
        The number of plots for detected events outputed for each station data.

    plot_mode: str, default='time'
        The type of plots: 'time': only time series or 'time_frequency', time and spectrograms.
          
    estimate_uncertainty: bool, default=False
        If True uncertainties in the output probabilities will be estimated.           

    number_of_sampling: int, default=5
        Number of sampling for the uncertainty estimation. 
               
    loss_weights: list, default=[0.03, 0.40, 0.58]
        Loss weights for detection, P picking, and S picking respectively.
             
    loss_types: list, default=['binary_crossentropy', 'binary_crossentropy', 'binary_crossentropy'] 
        Loss types for detection, P picking, and S picking respectively.

    input_dimention: tuple, default=(6000, 3)
        Loss types for detection, P picking, and S picking respectively.      

    normalization_mode: str, default='std' 
        Mode of normalization for data preprocessing, 'max', maximum amplitude among three components, 'std', standard deviation.
           
    batch_size: int, default=500 
        Batch size. This wont affect the speed much but can affect the performance. A value beteen 200 to 1000 is recommanded.

    gpuid: int, default=None
        Id of GPU used for the prediction. If using CPU set to None.
         
    gpu_limit: int, default=None
        Set the maximum percentage of memory usage for the GPU.
          
    number_of_cpus: int, default=5
        Number of CPUs used for the parallel preprocessing and feeding of data for prediction.

    use_multiprocessing: bool, default=True
        If True, multiple CPUs will be used for the preprocessing of data even when GPU is used for the prediction.        

    keepPS: bool, default=False
        If True, only detected events that have both P and S picks will be written otherwise those events with either P or S pick. 
        
    spLimit: int, default=60
        S - P time in seconds. It will limit the results to those detections with events that have a specific S-P time limit. 
        
    Returns
    -------- 
    ./output_dir/STATION_OUTPUT/X_prediction_results.csv: A table containing all the detection, and picking results. Duplicated events are already removed.      
    
    ./output_dir/STATION_OUTPUT/X_report.txt: A summary of the parameters used for prediction and performance.
    
    ./output_dir/STATION_OUTPUT/figures: A folder containing plots detected events and picked arrival times. 
    
    ./time_tracks.pkl: A file containing the time track of the continous data and its type.
    

    Notes
    --------
    Estimating the uncertainties requires multiple predictions and will increase the computational time. 
    
        
    """ 
   
    
    args = {
    "input_dir": input_dir,
    "input_hdf5": None,
    "input_csv": None,
    "input_model": input_model,
    "output_dir": output_dir,
    "output_probabilities": output_probabilities,
    "detection_threshold": detection_threshold,
    "P_threshold": P_threshold,
    "S_threshold": S_threshold,
    "number_of_plots": number_of_plots,
    "plot_mode": plot_mode,
    "estimate_uncertainty": estimate_uncertainty,
    "number_of_sampling": number_of_sampling,
    "loss_weights": loss_weights,     
    "loss_types": loss_types,
    "input_dimention": input_dimention,
    "normalization_mode": normalization_mode,
    "batch_size": batch_size,
    "gpuid": gpuid,
    "gpu_limit": gpu_limit,
    "number_of_cpus": number_of_cpus,
    "use_multiprocessing": use_multiprocessing,
    "keepPS": keepPS,
    "spLimit": spLimit   
    }
        
    availble_cpus = multiprocessing.cpu_count()
    if args['number_of_cpus'] > availble_cpus:
        args['number_of_cpus'] = availble_cpus
        
    if args['gpuid']:     
        os.environ['CUDA_VISIBLE_DEVICES'] = '{}'.format(args['gpuid'])
        tf.Session(config=tf.ConfigProto(log_device_placement=True))
        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        config.gpu_options.per_process_gpu_memory_fraction = float(args['gpu_limit']) 
        K.tensorflow_backend.set_session(tf.Session(config=config))          
                                  
    class DummyFile(object):
        file = None
        def __init__(self, file):
            self.file = file
    
        def write(self, x):
            # Avoid print() second call (useless \n)
            if len(x.rstrip()) > 0:
                tqdm.write(x, file=self.file)
    
    @contextlib.contextmanager
    def nostdout():
        save_stdout = sys.stdout
        sys.stdout = DummyFile(sys.stdout)
        yield
        sys.stdout = save_stdout
    process = psutil.Process(os.getpid())
    Membefore = process.memory_info().rss  # in bytes
    
    #karyogram()

    if isinstance(args['output_dir'], str):
        out_dir = os.path.join(os.getcwd(), str(args['output_dir']))
        #if os.path.isdir(out_dir):
        #    print('============================================================================')        
        #    print(f' *** {out_dir} already exists!')
        #    inp = input(" --> Type (Yes or y) to create a new empty directory! otherwise it will overwrite!   ")
        #    if inp.lower() == "yes" or inp.lower() == "y":
        #        shutil.rmtree(out_dir)  
        #        os.makedirs(out_dir) 
        if platform.system() == 'Windows': 
            station_list = [ev.split(".")[0] for ev in listdir(args["input_dir"]) if ev.split("\\")[-1] != ".DS_Store"];
        else:
            station_list = [ev.split(".")[0] for ev in listdir(args['input_dir']) if ev.split("/")[-1] != ".DS_Store"];
        station_list = sorted(set(station_list))
        
        #print(f"######### There are files for {len(station_list)} stations in {args['input_dir']} directory. #########", flush=True)
        for ct, st in enumerate(station_list):
            if platform.system() == 'Windows': 
                args["input_hdf5"] = args["input_dir"]+"\\"+st+".hdf5"
                args["input_csv"] = args["input_dir"]+"\\"+st+".csv"
            else:            
                args["input_hdf5"] = args["input_dir"]+"/"+st+".hdf5"
                args["input_csv"] = args["input_dir"]+"/"+st+".csv"
        
            save_dir = os.path.join(out_dir, str(st)+'_outputs')
            out_probs = os.path.join(save_dir, 'prediction_probabilities.hdf5')
            save_figs = os.path.join(save_dir, 'figures') 
            if os.path.isdir(save_dir):
                shutil.rmtree(save_dir)  
            os.makedirs(save_dir) 
            if args['number_of_plots']:
                os.makedirs(save_figs) 
            try:
                os.remove(out_probs)
            except Exception:
                 pass 
            
            if args['output_probabilities']:           
                HDF_PROB = h5py.File(out_probs, 'a')
                HDF_PROB.create_group("probabilities")
                HDF_PROB.create_group("uncertainties")  
            else:
                HDF_PROB = None   
                
            csvPr_gen = open(os.path.join(save_dir,'X_prediction_results.csv'), 'w')          
            predict_writer = csv.writer(csvPr_gen, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            predict_writer.writerow(['file_name', 
                                     'network',
                                     'station',
                                     'instrument_type',
                                     'station_lat',
                                     'station_lon',
                                     'station_elv',
                                     'event_start_time',
                                     '36_time',
                                     'detection_probability',
                                     'detection_uncertainty', 
                                     'p_arrival_time',
                                     'p_probability',
                                     'p_uncertainty',
                                     'p_snr',
                                     's_arrival_time',
                                     's_probability',
                                     's_uncertainty',
                                     's_snr'
                                         ])  
            csvPr_gen.flush()
#            print(f'========= Started working on {st}, {ct+1} out of {len(station_list)} ...', flush=True)
    
            start_Predicting = time.time()       
            detection_memory = []
            plt_n = 0
        
            df = pd.read_csv(args['input_csv']) 
            prediction_list = df.trace_name.tolist() 
            fl = h5py.File(args['input_hdf5'], 'r')    
            list_generator=generate_arrays_from_file(prediction_list, args['batch_size']) 
        
            pbar_test = tqdm(total= int(np.ceil(len(prediction_list)/args['batch_size'])), ncols=100, file=sys.stdout)        
            for bn in range(int(np.ceil(len(prediction_list) / args['batch_size']))):  
                with nostdout():              
                    pbar_test.update()
                    
                new_list = next(list_generator)  
                prob_dic=_gen_predictor(new_list, args, input_model)
        
                pred_set={}
                for ID in new_list:
                    dataset = fl.get('data/'+str(ID))
                    pred_set.update( {str(ID) : dataset})  
                    
                plt_n, detection_memory= _gen_writer(new_list, args, prob_dic, pred_set, HDF_PROB, predict_writer, save_figs, csvPr_gen, plt_n, detection_memory, keepPS, spLimit)    
    
            end_Predicting = time.time() 
            delta = (end_Predicting - start_Predicting) 
            hour = int(delta / 3600)
            delta -= hour * 3600
            minute = int(delta / 60)
            delta -= minute * 60
            seconds = delta     
            
            
            dd = pd.read_csv(os.path.join(save_dir,'X_prediction_results.csv'))
#            print(f'\n', flush=True)
            print(' *** Finished the prediction in: {} hours and {} minutes and {} seconds.'.format(hour, minute, round(seconds, 2)), flush=True)         
            print(' *** Detected: '+str(len(dd))+' events.', flush=True)
            p_arrival_time = 'Nan'
            s_arrival_time = 'Nan'
            if(dd.empty==False):
                p_arrival_time = dd['p_arrival_time'][0]
                s_arrival_time = dd['s_arrival_time'][0]
    return p_arrival_time,s_arrival_time,delta
            
def _gen_predictor(new_list, args, model): 
    
    
    """ 
    
    Performs the predictions for the current batch.

    Parameters
    ----------
    new_list: list of str
        A list of trace names in the batch.
    args: dic
        A dictionary containing all of the input parameters. 

    model: 
        The compiled model used for the prediction.

    Returns
    -------
    prob_dic: dic
        A dictionary containing output probabilities and their estimated standard deviations.
        
    """    
    
    prob_dic = dict()            
    params_prediction = {'file_name': str(args['input_hdf5']), 
                         'dim': args['input_dimention'][0],
                         'batch_size': len(new_list),
                         'n_channels': args['input_dimention'][-1],
                         'norm_mode': args['normalization_mode']}     
            
    prediction_generator = DataGeneratorPrediction(new_list, **params_prediction)
    if args['estimate_uncertainty']:
        if not args['number_of_sampling'] or args['number_of_sampling'] <= 0:
            print('please define the number of Monte Carlo sampling!')
        
        pred_DD = []
        pred_PP = []
        pred_SS = []          
        for mc in range(args['number_of_sampling']):
            predD, predP, predS = model.predict_generator(generator = prediction_generator,
                                                          use_multiprocessing = args['use_multiprocessing'],
                                                          workers = args['number_of_cpus'])
            pred_DD.append(predD)
            pred_PP.append(predP)               
            pred_SS.append(predS)
                            
        pred_DD = np.array(pred_DD).reshape(args['number_of_sampling'], len(new_list), params_prediction['dim'])
        pred_DD_mean = pred_DD.mean(axis=0)
        pred_DD_std = pred_DD.std(axis=0)  
                
        pred_PP = np.array(pred_PP).reshape(args['number_of_sampling'], len(new_list), params_prediction['dim'])
        pred_PP_mean = pred_PP.mean(axis=0)
        pred_PP_std = pred_PP.std(axis=0)      
                    
        pred_SS = np.array(pred_SS).reshape(args['number_of_sampling'], len(new_list), params_prediction['dim'])
        pred_SS_mean = pred_SS.mean(axis=0)
        pred_SS_std = pred_SS.std(axis=0)                       
    else:          
        pred_DD_mean, pred_PP_mean, pred_SS_mean = model.predict_generator(generator = prediction_generator,
                                                                           use_multiprocessing = args['use_multiprocessing'],
                                                                           workers = args['number_of_cpus'])
        pred_DD_mean = pred_DD_mean.reshape(pred_DD_mean.shape[0], pred_DD_mean.shape[1]) 
        pred_PP_mean = pred_PP_mean.reshape(pred_PP_mean.shape[0], pred_PP_mean.shape[1]) 
        pred_SS_mean = pred_SS_mean.reshape(pred_SS_mean.shape[0], pred_SS_mean.shape[1]) 
                    
        pred_DD_std = np.zeros((pred_DD_mean.shape))
        pred_PP_std = np.zeros((pred_PP_mean.shape))
        pred_SS_std = np.zeros((pred_SS_mean.shape))   
                
    prob_dic['DD_mean']=pred_DD_mean   
    prob_dic['PP_mean']=pred_PP_mean   
    prob_dic['SS_mean']=pred_SS_mean   
    prob_dic['DD_std']=pred_DD_std   
    prob_dic['PP_std']=pred_PP_std   
    prob_dic['SS_std']=pred_SS_std  
    
    return prob_dic  
     
      
    
def _gen_writer(new_list, args, prob_dic, pred_set, HDF_PROB, predict_writer, save_figs, csvPr_gen, plt_n, detection_memory, keepPS, spLimit):
    
    """ 
    
    Applies the detection and picking on the output predicted probabilities and if it founds any, write them out in the CSV file,
    makes the plots, and save the probabilities and uncertainties.

    Parameters
    ----------
    new_list: list of str
        A list of trace names in the batch.

    args: dic
        A dictionary containing all of the input parameters. 

    prob_dic: dic
        A dictionary containing output probabilities and their estimated standard deviations.
        
    pred_set: dic
        A dictionary containing HDF datasets for the current batch. 

    HDF_PROB: obj
        For writing out the probabilities and uncertainties. 

    predict_writer: obj
        For writing out the detection/picking results in the CSV file.    
    
    save_figs: str
        Path to the folder for saving the plots. 

    csvPr_gen : obj
        For writing out the detection/picking results in the CSV file.   
    
    plt_n: positive integer
        Keep the track of plotted figures.     

    detection_memory: list
        Keep the track of detected events.  

    spLimit: int, default : 60
        S - P time in seconds. It will limit the results to those detections with events that have a specific S-P time limit.
        
    Returns
    -------
    plt_n: positive integer
        Keep the track of plotted figures. 
        
    detection_memory: list
        Keep the track of detected events.  
        
        
    """    
    
    for ts in range(prob_dic['DD_mean'].shape[0]): 
        evi =  new_list[ts] 
        dataset = pred_set[evi]  
        dat = np.array(dataset)


        if args['output_probabilities']: 
            
            probs = np.zeros((prob_dic['DD_mean'].shape[1], 3))
            probs[:, 0] = prob_dic['DD_mean'][ts]
            probs[:, 1] = prob_dic['PP_mean'][ts]
            probs[:, 2] = prob_dic['SS_mean'][ts]
             
            uncs = np.zeros((prob_dic['DD_mean'].shape[1], 3))
            uncs[:, 0] = prob_dic['DD_std'][ts]
            uncs[:, 1] = prob_dic['PP_std'][ts]
            uncs[:, 2] = prob_dic['SS_std'][ts]
            
            HDF_PROB.create_dataset('probabilities/'+str(evi), probs.shape, data=probs, dtype= np.float32) 
            HDF_PROB.create_dataset('uncertainties/'+str(evi), uncs.shape, data=uncs, dtype= np.float32) 
            HDF_PROB.flush()
                               
        matches, pick_errors, yh3 =  picker(args, prob_dic['DD_mean'][ts], prob_dic['PP_mean'][ts], prob_dic['SS_mean'][ts],
                                            prob_dic['DD_std'][ts], prob_dic['PP_std'][ts], prob_dic['SS_std'][ts])
        if keepPS:
            if (len(matches) >= 1) and (matches[list(matches)[0]][3] and matches[list(matches)[0]][6]):
                if (matches[list(matches)[0]][6] - matches[list(matches)[0]][3]) < spLimit*100:
                    snr = [_get_snr(dat, matches[list(matches)[0]][3], window = 100), _get_snr(dat, matches[list(matches)[0]][6], window = 100)] 
                    pre_write = len(detection_memory)
                    detection_memory=_output_writter_prediction(dataset, predict_writer, csvPr_gen, matches, snr, detection_memory)
                    post_write = len(detection_memory)
                    if plt_n < args['number_of_plots'] and post_write > pre_write:
                        plt_n += 1 ; 
        else:
            if (len(matches) >= 1) and ((matches[list(matches)[0]][3] or matches[list(matches)[0]][6])):
                snr = [_get_snr(dat, matches[list(matches)[0]][3], window = 100), _get_snr(dat, matches[list(matches)[0]][6], window = 100)] 
                pre_write = len(detection_memory)
                detection_memory=_output_writter_prediction(dataset, predict_writer, csvPr_gen, matches, snr, detection_memory)
                post_write = len(detection_memory)
                if plt_n < args['number_of_plots'] and post_write > pre_write:
                    plt_n += 1 ; 
           
                    
    return plt_n, detection_memory



def _output_writter_prediction(dataset, predict_writer, csvPr, matches, snr, detection_memory):
    
    """ 
    
    Writes the detection & picking results into a CSV file.

    Parameters
    ----------
    dataset: hdf5 obj
        Dataset object of the trace.

    predict_writer: obj
        For writing out the detection/picking results in the CSV file.
        
    csvPr: obj
        For writing out the detection/picking results in the CSV file.  

    matches: dic
        It contains the information for the detected and picked event.   
 
    snr: list of two floats
        Estimated signal to noise ratios for picked P and S phases.      
 
    detection_memory : list
        Keep the track of detected events.          
        
    Returns
    -------   
    detection_memory : list
        Keep the track of detected events.  
        
        
    """      

    trace_name = dataset.attrs["trace_name"]
    station_name = dataset.attrs["receiver_code"]
    station_lat = dataset.attrs["receiver_latitude"]
    station_lon = dataset.attrs["receiver_longitude"]
    station_elv = dataset.attrs["receiver_elevation_m"]
    start_time = dataset.attrs["trace_start_time"]
    station_name = "{:<4}".format(station_name)
    network_name = dataset.attrs["network_code"]
    network_name = "{:<2}".format(network_name)
    instrument_type = trace_name.split('_')[2]
    instrument_type = "{:<2}".format(instrument_type)  

    try:
        start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S.%f')
    except Exception:
        start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        
    def _date_convertor(r):  
        if isinstance(r, str):
            mls = r.split('.')
            if len(mls) == 1:
                new_t = datetime.strptime(r, '%Y-%m-%d %H:%M:%S')
            else:
                new_t = datetime.strptime(r, '%Y-%m-%d %H:%M:%S.%f')
        else:
            new_t = r
            
        return new_t
            
    for match, match_value in matches.items():
        ev_strt = start_time+timedelta(seconds= match/100)
        ev_end = start_time+timedelta(seconds= match_value[0]/100)
        
        doublet = [ st for st in detection_memory if abs((st-ev_strt).total_seconds()) < 2]
        
        if len(doublet) == 0: 
            det_prob = round(match_value[1], 2)
            if match_value[2]:
                det_unc = round(match_value[2], 2) 
            else:
                det_unc = match_value[2]
                       
            if match_value[3]: 
                p_time = start_time+timedelta(seconds= match_value[3]/100)
            else:
                p_time = None
            p_prob = match_value[4]
            p_unc = match_value[5]
            
            if p_unc:
                p_unc = round(p_unc, 2)
            if p_prob:
                p_prob = round(p_prob, 2)
                
            if match_value[6]:
                s_time = start_time+timedelta(seconds= match_value[6]/100)
            else:
                s_time = None
            s_prob = match_value[7]
            s_unc = match_value[8]

            if s_unc:
                s_unc = round(s_unc, 2)                
            if s_prob:
                s_prob = round(s_prob, 2)
                
            predict_writer.writerow([trace_name, 
                                         network_name,
                                         station_name, 
                                         instrument_type,
                                         station_lat, 
                                         station_lon,
                                         station_elv,
                                         _date_convertor(ev_strt), 
                                         _date_convertor(ev_end), 
                                         det_prob, 
                                         det_unc,                                
                                         _date_convertor(p_time), 
                                         p_prob,
                                         p_unc,
                                         snr[0],
                                         _date_convertor(s_time), 
                                         s_prob,
                                         s_unc, 
                                         snr[1]
                                         ]) 
            
            csvPr.flush()
            detection_memory.append(ev_strt)
            
    return detection_memory
            







def _get_snr(data, pat, window = 200):
    
    """ 
    
    Estimates SNR.
    
    Parameters
    ----------
    data: NumPy array
        3 component data.     

    pat: positive integer
        Sample point where a specific phase arrives.  

    window: positive integer
        The length of the window for calculating the SNR (in the sample).         
        
    Returns
    -------   
    snr : {float, None}
       Estimated SNR in db.   
        
    """      
       
    snr = None
    if pat:
        try:
            if int(pat) >= window and (int(pat)+window) < len(data):
                nw1 = data[int(pat)-window : int(pat)];
                sw1 = data[int(pat) : int(pat)+window];
                snr = round(10*math.log10((np.percentile(sw1,95)/np.percentile(nw1,95))**2), 1)           
            elif int(pat) < window and (int(pat)+window) < len(data):
                window = int(pat)
                nw1 = data[int(pat)-window : int(pat)];
                sw1 = data[int(pat) : int(pat)+window];
                snr = round(10*math.log10((np.percentile(sw1,95)/np.percentile(nw1,95))**2), 1)
            elif (int(pat)+window) > len(data):
                window = len(data)-int(pat)
                nw1 = data[int(pat)-window : int(pat)];
                sw1 = data[int(pat) : int(pat)+window];
                snr = round(10*math.log10((np.percentile(sw1,95)/np.percentile(nw1,95))**2), 1)    
        except Exception:
            pass
    return snr 


