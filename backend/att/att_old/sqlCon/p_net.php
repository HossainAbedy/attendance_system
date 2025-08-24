<?php	
//date_default_timezone_set("Asia/Dhaka");
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
 


$sql="SELECT [nEventLogIdn]
      ,[nDateTime]
      ,[nReaderIdn]
      ,[nEventIdn]
      ,[nUserID]
      ,[nIsLog]
      ,[nTNAEvent]
      ,[nIsUseTA]
      ,[nType]
  FROM [BioStar].[dbo].[TB_EVENT_LOG] where nUserID='302'";
  
$stmt = sqlsrv_query( $conn, $sql );
if( $stmt === false) {
    die( print_r( sqlsrv_errors(), true) );
}

while( $row = sqlsrv_fetch_array( $stmt, SQLSRV_FETCH_ASSOC) ) {
      echo date("Y-m-d H:i:s", $row['nDateTime']).", ".$row['nUserID']."<br />";
      $name=$row['nReaderIdn'];
      
      //$q=mysql_query("insert into users(first_name) values('$name')");
}

sqlsrv_free_stmt( $stmt);


?>