### Technology stack ###

Front-end: React v19.3
Back-end: Python
Database: Google Cloud
Data-source: Data originally qeuried from Amazon AWS3 (nasa-irsa-spherex)


### User Interface ###
- Field for user to enter coordinates (ra_deg, dec_deg)
- Extra features(Optional features for the application)
  - 1. On hover, per pixel (CursorInfo)
  - Field of view
  - Wavelength range (em_min, em_max)
  - ZODI value (How much the image is background)
  - Signal-to-noise (signal ÷ error)
  - Surface brightness ± error (MJy/sr), from IMAGE and √VARIANCE (The real value, not the PNG brightness)
  - Flag names set on that pixel (GHOST, PERSIST, STREAK…) (Flags at the end of file)
  - Wavelength ± bandwidth (µm) (What the pixel actually measured)
### Requirements ###
- Your challenge is to create a public-facing web tool to display images of the sky from the SPHEREx mission, 
- making it easy for anyone to quickly see how they change over time. 
- Users will enter the coordinates of a patch of sky (Right Ascension and declination). 
- Your tool will display a series of images of that patch like a little video, making it easy to spot moving objects.
- 
- Must work on mobile
-
- Data originally qeuried from Amazon AWS3 (nasa-irsa-spherex)

# Data flow #
- 1. User enters coordinates(ra_deg, dec_deg)
- 2. Database (Amazon AWS3) queried with Fast API 
- 3. FITS file is returned to Google Cloud
- 4. FITS data taken from Google Cloud and from dataset PNG files taken
- 4. PNG images for that query are made into a gif
- 5. gif is showed to the user

- X. Queries stored in cache memory for faster results on same queries


### Flags ###
HIERARCH L2 N_NONLINEAR = 0 / number of pixels flagged nonlinear                
HIERARCH L2 N_PERSIST = 23502 / number of pixels flagged persist                
HIERARCH L2 N_HOT =                    1 / number of pixels flagged hot         
HIERARCH L2 N_COLD = 1307 / number of pixels flagged cold                       
HIERARCH L2 N_TRAN_NB = 23511 / number of not bad transient pixels              
HIERARCH L2 N_PERS_NB = 23498 / number of persistence and not bad pixels        
HIERARCH L2 N_SOURCE = 4135535 / number of source flagged pixels                
HIERARCH L2 N_XTALK = 53262 / number of crosstalk flagged pixels                
HIERARCH L2 N_GHOST = 0 / number of ghost flagged pixels                        
HIERARCH L2 N_GHOST_FPA = 0 / number of ghost_fpa flagged pixels                
HIERARCH L2 N_GHOST_EXT = 0 / number of ghost_ext flagged pixels                
HIERARCH L2 N_BLOOM_NS = 0 / number of BLOOM flagged pixels not flagged SOURCE  
HIERARCH L2 N_SNOW_NS = 0 / number of SNOW flagged pixels not flagged SOURCE    
HIERARCH L2 N_OUTLIER = 842 / number of flagged outlier pixels                  
HIERARCH L2 N_TRANSIENT = 31044 / number of flagged flagged transient pixels    
HIERARCH L2 N_OVERFLOW = 2976 / number of flagged overflow pixels               
HIERARCH L2 N_SUR_ERROR = 20025 / number of flagged sur error pixels            
HIERARCH L2 N_NONFUNC = 10924 / number of flagged nonfunctional pixels          
HIERARCH L2 N_DICHROIC = 0 / number of flagged pixels due to low efficiency     
HIERARCH L2 N_MISSING = 0 / number of flagged pixels with missing data          
HIERARCH L2 N_FULLSAMPLE = 240 / number of flagged full-sample pixels           
HIERARCH L2 N_PHANMISS = 0 / number of flagged phanmiss pixels                  
HIERARCH L2 N_SNOWBALL = 84 / number of flagged snowball artifact pixels        
HIERARCH L2 N_BLOOM = 7944 / number of flagged bloom artifact pixels            
HIERARCH L2 N_HALO = 71118 / number of flagged transient halo pixels            
HIERARCH L2 N_SAT_HALO = 0 / number of flagged streak halo pixels 
###