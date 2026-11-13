import Aptabase from '@aptabase/react-native';
import {Platform} from 'react-native';
import {createUsage,isAnalyticsDevice} from './usage';

// Public ingestion key, not an account/admin credential. A-EU selects EU hosting.
export const aptabaseAppKey='A-EU-3618719023';
const enabled=isAnalyticsDevice(Platform.OS,Platform.constants);
if(enabled)Aptabase.init(aptabaseAppKey,{enableWeb:false,enableCrashReporting:false,flushInterval:10000});
export const usage=createUsage((event,props)=>{if(enabled)Aptabase.trackEvent(event,props);});
