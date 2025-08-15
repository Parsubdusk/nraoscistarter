#!/usr/bin/env python3
"""
SDR Sharp Auto-Configuration for RFI Detection
Automatically configures SDR Sharp with optimal settings for radio astronomy RFI monitoring
"""
import os
import xml.etree.ElementTree as ET
import shutil
import logging
from pathlib import Path

class SDRSharpConfigurator:
    def __init__(self, sdr_path, audio_output_path):
        self.sdr_path = Path(sdr_path)
        self.audio_output_path = Path(audio_output_path)
        self.config_file = self.sdr_path / "SDRSharp.exe.config"
        
    def create_optimal_config(self):
        """Create optimal SDR Sharp configuration for RFI detection"""
        try:
            # Ensure audio output directory exists
            self.audio_output_path.mkdir(parents=True, exist_ok=True)
            
            # Backup existing config if it exists
            if self.config_file.exists():
                backup_file = self.config_file.with_suffix('.config.backup')
                shutil.copy2(self.config_file, backup_file)
                logging.info(f"Backed up existing config to {backup_file}")
            
            # Create optimized configuration
            config_xml = self._generate_config_xml()
            
            # Write configuration file
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(config_xml)
            
            logging.info("SDR Sharp configuration created successfully")
            return True
            
        except Exception as e:
            logging.error(f"Failed to create SDR Sharp config: {str(e)}")
            return False
    
    def _generate_config_xml(self):
        """Generate optimized SDR Sharp configuration XML"""
        audio_path_normalized = str(self.audio_output_path).replace('\\', '\\\\')
        
        config = f"""<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <configSections>
    <sectionGroup name="userSettings" type="System.Configuration.UserSettingsGroup, System, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089">
      <section name="SDRSharp.Properties.Settings" type="System.Configuration.ClientSettingsSection, System, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089" allowExeDefinition="MachineToLocalUser" requirePermission="false" />
    </sectionGroup>
  </configSections>
  <userSettings>
    <SDRSharp.Properties.Settings>
      <!-- Audio Recording Settings for RFI Detection -->
      <setting name="AudioRecordingEnabled" serializeAs="String">
        <value>True</value>
      </setting>
      <setting name="AudioRecordingFormat" serializeAs="String">
        <value>WAV</value>
      </setting>
      <setting name="AudioRecordingSampleRate" serializeAs="String">
        <value>48000</value>
      </setting>
      <setting name="AudioRecordingBitDepth" serializeAs="String">
        <value>16</value>
      </setting>
      <setting name="AudioRecordingPath" serializeAs="String">
        <value>{audio_path_normalized}</value>
      </setting>
      <setting name="AudioRecordingAutoStart" serializeAs="String">
        <value>False</value>
      </setting>
      
      <!-- SDR Configuration for RFI Detection -->
      <setting name="SampleRate" serializeAs="String">
        <value>2400000</value>
      </setting>
      <setting name="RFGain" serializeAs="String">
        <value>25</value>
      </setting>
      <setting name="IFGain" serializeAs="String">
        <value>22</value>
      </setting>
      <setting name="AudioGain" serializeAs="String">
        <value>50</value>
      </setting>
      
      <!-- Frequency Settings -->
      <setting name="Frequency" serializeAs="String">
        <value>146000000</value>
      </setting>
      <setting name="DetectorType" serializeAs="String">
        <value>WFM</value>
      </setting>
      <setting name="FilterBandwidth" serializeAs="String">
        <value>200000</value>
      </setting>
      
      <!-- Display Settings -->
      <setting name="WaterfallAttack" serializeAs="String">
        <value>0.9</value>
      </setting>
      <setting name="WaterfallDecay" serializeAs="String">
        <value>0.6</value>
      </setting>
      <setting name="SpectrumAnalyzerAttack" serializeAs="String">
        <value>0.9</value>
      </setting>
      <setting name="SpectrumAnalyzerDecay" serializeAs="String">
        <value>0.4</value>
      </setting>
      
      <!-- RFI Detection Optimizations -->
      <setting name="AGCEnabled" serializeAs="String">
        <value>False</value>
      </setting>
      <setting name="AGCThreshold" serializeAs="String">
        <value>-20</value>
      </setting>
      <setting name="SquelchEnabled" serializeAs="String">
        <value>False</value>
      </setting>
      
      <!-- Window and UI -->
      <setting name="WindowState" serializeAs="String">
        <value>Normal</value>
      </setting>
      <setting name="CenterFrequency" serializeAs="String">
        <value>146000000</value>
      </setting>
    </SDRSharp.Properties.Settings>
  </userSettings>
  
  <startup>
    <supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8" />
  </startup>
</configuration>"""
        return config
    
    def create_preset_frequencies(self):
        """Create frequency presets for common RFI monitoring bands"""
        presets = {
            "Ham 2m": 146000000,
            "Ham 70cm": 432000000,
            "WiFi 2.4GHz": 2400000000,
            "Cell 850MHz": 850000000,
            "FM Broadcast": 100000000,
            "Hydrogen Line": 1420405751,
            "Radio Quiet": 73000000
        }
        
        preset_file = self.sdr_path / "RFI_Presets.xml"
        
        try:
            root = ET.Element("presets")
            
            for name, freq in presets.items():
                preset = ET.SubElement(root, "preset")
                ET.SubElement(preset, "name").text = name
                ET.SubElement(preset, "frequency").text = str(freq)
                ET.SubElement(preset, "mode").text = "WFM"
                ET.SubElement(preset, "bandwidth").text = "200000"
            
            tree = ET.ElementTree(root)
            tree.write(preset_file, encoding='utf-8', xml_declaration=True)
            
            logging.info(f"Created RFI frequency presets: {preset_file}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to create frequency presets: {str(e)}")
            return False

def configure_sdr_sharp(sdr_path, audio_path):
    """Configure SDR Sharp for optimal RFI detection"""
    configurator = SDRSharpConfigurator(sdr_path, audio_path)
    
    success = configurator.create_optimal_config()
    if success:
        configurator.create_preset_frequencies()
    
    return success

if __name__ == '__main__':
    # Test configuration
    sdr_path = r"C:\Users\coraj\OneDrive\Desktop\sdrsharp-x86"
    audio_path = r"C:\Users\coraj\OneDrive\Desktop\Audio"
    
    success = configure_sdr_sharp(sdr_path, audio_path)
    if success:
        print("✓ SDR Sharp configured for optimal RFI detection")
        print("✓ Audio recording automatically set to save in monitored directory")
        print("✓ Frequency presets created for common RFI sources")
    else:
        print("✗ Configuration failed")
