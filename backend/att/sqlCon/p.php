<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>CHOKH</title>
 
<script language="javascript" type="text/javascript" src="script.js"></script>
<script>
 $(document).ready(function(){
 setInterval(function(){cache_clear()},1000000);
 });
 function cache_clear()
{
 //window.location.reload(true); //use this if you do remove cache
  window.location.reload(); 
}
</script> 
</head>
<body>
<?php	

echo date("H:i:s");
echo "<br>";
include("database.php");
include("database1.php");



$sql="SELECT [nEventLogIdn]
	 ,dateadd(s,[nDateTime],'19700101 00:00:00:000') as attDateTime
      ,[nDateTime]
      ,[nReaderIdn]
      ,[nEventIdn]
      ,[nUserID]
      ,[nIsLog]
      ,[nTNAEvent]
      ,[nIsUseTA]
      ,[nType]
  FROM [BioStar].[dbo].[TB_EVENT_LOG] where nUserID>0 and nEventIdn=55
";
  
$stmt = sqlsrv_query( $conn, $sql );
if( $stmt === false) {
    die( print_r( sqlsrv_errors(), true) );
}

while( $row = sqlsrv_fetch_array( $stmt, SQLSRV_FETCH_ASSOC) ) 
{
//echo $logDate=date("Y-m-d", $row['nDateTime']);
//echo "<br>";
echo $row['nUserID'];
echo "<br>";
echo $logDate=$row['attDateTime']->format('Y-m-d');
//echo $logTime=date("H:i:s", $row['nDateTime']);
echo "<br>";
echo $logTime=$row['attDateTime']->format('H:i:s');
//echo $row['attDateTime']->format('Y-m-d H:i:s');
echo "<br>";
echo $logEvent=$row['nEventIdn'];
echo "<br>";
echo "<br>";

$q=mysql_query("insert into  att_raw_data values('null', '$logDate', '$row[nUserID]', '$row[nUserID]', '', '$logTime', '$row[nReaderIdn]', '$logEvent')");
}

sqlsrv_free_stmt( $stmt);

?>

</body>