###################################################################################################################
#                                                                                                                 #
#   This file handles all the processes done when performing Pyradiomics and shows a progress bar while doing it  #
#                                                                                                                 #
###################################################################################################################

import os
import sys
import pandas as pd
import SimpleITK as sitk
from pydicom import dcmread
from radiomics import featureextractor
from src.Model.LoadPatients import get_datasets
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QMessageBox, QDesktopWidget
import radiomics


class PyradiExtended(QtCore.QThread):
    copied_percent_signal = QtCore.pyqtSignal(int, str)
    
    def __init__(self, path, filepaths, target_path):
        super().__init__()
        self.path = path 
        self.filepaths = filepaths
        self.target_path = target_path
        
    def run(self):
        """
        Perform pyradiomics analysis
        """
        self.my_callback(0, '')

        # Read one ct file, done to later obtain patient hash 
        ct_file = dcmread(self.filepaths[0], force=True)
        # Read RT-Struct file
        rtss_path = self.filepaths['rtss']

        if self.target_path == '':
            patient_hash = os.path.basename(ct_file.PatientID)
            # Name of nrrd file
            nrrd_file_name = patient_hash + '.nrrd'  
            # Location of folder where nrrd file saved
            nrrd_folder_path = self.path + '/nrrd/'
            # Location of folder where pyradiomics output saved
            csv_path = self.path + '/CSV/'
        else:
            patient_hash = os.path.basename(self.target_path)
            # Name of nrrd file
            nrrd_file_name = patient_hash + '.nrrd'  
            # Location of folder where nrrd file saved
            nrrd_folder_path = self.target_path + '/nrrd/'
            # Location of folder where pyradiomics output saved
            csv_path = self.target_path + '/CSV/'
    
        # Complete path of converted file
        nrrd_file_path = nrrd_folder_path + \
            nrrd_file_name  

        # If folder does not exist
        if not os.path.exists(nrrd_folder_path):
            # Create folder  
            os.makedirs(nrrd_folder_path)

        self.convert_to_nrrd(self.path, nrrd_file_path, self.my_callback)

        # Location of folder where converted masks saved
        mask_folder_path = nrrd_folder_path + \
            'structures'  
        self.convert_rois_to_nrrd(self.path, rtss_path, mask_folder_path, self.my_callback)

        # Something went wrong, in this case PyRadiomics will also log an error
        if nrrd_file_path is None or nrrd_folder_path is None:
            print('Error getting testcase!')
            exit()

        radiomics_df = self.get_radiomics_df(
            self.path, patient_hash, nrrd_file_path, mask_folder_path, self.my_callback)
        self.convert_df_to_csv(radiomics_df, patient_hash, csv_path, self.my_callback)


    def my_callback(self, percent, roi_name):
        self.copied_percent_signal.emit(percent, roi_name)

    def convert_to_nrrd(self, path, nrrd_file_path, callback):
        """ 
        Convert dicom files to nrrd.
        
        :param path:            Path to patient directory (str)
        
        :param nrrd_file_path:  Path to nrrd folder (str)
        
        :param callback:        Function to update progress bar
        """
        cmd_for_nrrd = 'plastimatch convert --input ' + path + \
            ' --output-img ' + nrrd_file_path + ' 1>' + path + '/NUL'
        cmd_del_nul = 'rm ' + path + '/NUL'
        # reader = sitk.ImageSeriesReader()
        # dicomReader = reader.GetGDCMSeriesFileNames(path)
        # reader.SetFileNames(dicomReader)
        # dicoms = reader.Execute()
        # sitk.WriteImage(dicoms, nrrd_file_path)
        callback(5, '')
        os.system(cmd_for_nrrd)
        os.system(cmd_del_nul)
        callback(25, '')


    def convert_rois_to_nrrd(self, path, rtss_path, mask_folder_path, callback):
        """ 
        Convert rtstruct to nrrd

        :param path:                Path to patient directory (str)
        
        :param rtss_path:           Path to RT-Struct file (str)

        :param mask_folder_path:    Folder to which the segmentation masks will be saved(str)
        
        :param callback:            Function to update progress bar
        """
        # Each ROI is saved in separate nrrd files
        cmd_for_segmask = 'plastimatch convert --input ' + rtss_path + ' --output-prefix ' + \
            mask_folder_path + ' --prefix-format nrrd --referenced-ct ' + \
            path + ' 1>' + path + '/NUL'
        cmd_del_nul = 'rm ' + path + '/NUL'
        os.system(cmd_for_segmask)
        os.system(cmd_del_nul)
        callback(50, '')


    def get_radiomics_df(self, path, patient_hash, nrrd_file_path, mask_folder_path, callback):
        """
        Run pyradiomics and return pandas dataframe with all the computed data
        """
        
        # Initialize feature extractor using default pyradiomics settings
        # Default features:
        #   first order, glcm, gldm, glrlm, glszm, ngtdm, shape
        # Default settings:
        #   'minimumROIDimensions': 2, 'minimumROISize': None, 'normalize': False,
        #   'normalizeScale': 1, 'removeOutliers': None, 'resampledPixelSpacing': None,
        #   'interpolator': 'sitkBSpline', 'preCrop': False, 'padDistance': 5, 'distances': [1],
        #   'force2D': False, 'force2Ddimension': 0, 'resegmentRange': None, 'label': 1,
        #   'additionalInfo': True
        extractor = featureextractor.RadiomicsFeatureExtractor()

        print("Calculating features")

        num_masks = len([file for file in os.listdir(mask_folder_path)])
        progress_increment = (50/num_masks)
        progress_percent = 50

        # Contains the features for all the ROI
        all_features = []
        # CSV headers
        radiomics_headers = []
        feature_vector = ''

        for file in os.listdir(mask_folder_path):
            # Contains features for current ROI
            roi_features = [] 
            roi_features.append(patient_hash)
            roi_features.append(path)
            # Full path of ROI nrrd file
            mask_name = mask_folder_path + '/' + file
            # Name of ROI  
            image_id = file.split('.')[0]  

            callback(progress_percent, image_id)

            feature_vector = extractor.execute(nrrd_file_path, mask_name)
            roi_features.append(image_id)

            # Add first order features to list
            for feature_name in feature_vector.keys():  
                roi_features.append(feature_vector[feature_name])

            all_features.append(roi_features)
            progress_percent += progress_increment

        radiomics_headers.append('Hash ID')
        radiomics_headers.append('Directory Path')
        radiomics_headers.append('ROI')

        # Extract column/feature names
        for feature_name in feature_vector.keys():
            radiomics_headers.append(feature_name)

        # Convert into dataframe
        radiomics_df = pd.DataFrame(all_features, columns=radiomics_headers)

        radiomics_df.set_index('Hash ID', inplace=True)

        return radiomics_df


    def convert_df_to_csv(self, radiomics_df, patient_hash, csv_path, callback):
        # If folder does not exist
        if not os.path.exists(csv_path):
            # Create folder  
            os.makedirs(csv_path)  

        # Export dataframe as csv
        radiomics_df.to_csv(csv_path + 'Pyradiomics_' +
                            patient_hash + '.csv')
        
        callback(100, '')
