<?php	

//dl('php_pdo_sqlsrv_7_ts_x64.dll'); 
$serverName = "172.19.11.106"; //serverName\instanceName
// Since UID and PWD are not specified in the $connectionInfo array,
// The connection will be attempted using Windows Authentication.
$connectionInfo = array( "Database"=>"BioStar", "UID"=>"sa", "PWD"=>"abc123X");
$conn = sqlsrv_connect( $serverName, $connectionInfo);

if( !$conn )
{
     echo "Connection could not be established.<br />";
     die( print_r( sqlsrv_errors(), true));
}
  
?>