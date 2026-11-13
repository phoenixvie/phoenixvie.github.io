import Aptabase from '@aptabase/react-native';
import {createUsage} from './usage';

// Public ingestion key, not an account/admin credential. A-EU selects EU hosting.
export const aptabaseAppKey='A-EU-3618719023';
Aptabase.init(aptabaseAppKey,{enableWeb:false,enableCrashReporting:false,flushInterval:10000});
export const usage=createUsage((event,props)=>Aptabase.trackEvent(event,props));
