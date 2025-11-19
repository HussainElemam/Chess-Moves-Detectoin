package com.example.chess_moves_tracking

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import org.opencv.android.OpenCVLoader
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private val channelName = "vision_bridge"
    private lateinit var engineVision: BoardEngine
    private val bg = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!OpenCVLoader.initDebug()) error("OpenCV failed to init")
        engineVision = BoardEngine(this, modelAsset = "pieces.tflite")
        // Camera permission handled on Dart side typically, but keep this sanity check:
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED) {
            // Dart should request permission before calling the channel.
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "inferFenFromYUV420" -> {
                        val w = call.argument<Int>("width")!!
                        val h = call.argument<Int>("height")!!
                        val y = call.argument<ByteArray>("bytesY")!!
                        val u = call.argument<ByteArray>("bytesU")!!
                        val v = call.argument<ByteArray>("bytesV")!!
                        val strideY = call.argument<Int>("strideY")!!
                        val strideU = call.argument<Int>("strideU")!!
                        val strideV = call.argument<Int>("strideV")!!
                        val pxU = call.argument<Int>("pixelStrideU")!!
                        val pxV = call.argument<Int>("pixelStrideV")!!
                        val processEvery = call.argument<Int>("processEvery") ?: 3
                        bg.execute {
                            val fenOrNull = engineVision.processYuvAndGetFen(
                                w,h,y,u,v,strideY,strideU,strideV,pxU,pxV, processEvery
                            )
                            runOnUiThread { result.success(fenOrNull) } // null means no stable change yet
                        }
                    }
                    "setGameId" -> {
                        val gameId = call.argument<String?>("gameId")
                        bg.execute {
                            engineVision.setGameId(gameId)
                            runOnUiThread { result.success(true) }
                        }
                    }
                    "saveLogs" -> {
                        bg.execute {
                            val logPath = engineVision.saveLogs()
                            runOnUiThread {
                                if (logPath != null) {
                                    result.success(logPath)
                                } else {
                                    result.success(null)
                                }
                            }
                        }
                    }
                    "clearLogs" -> {
                        bg.execute {
                            engineVision.clearLogs()
                            runOnUiThread { result.success(true) }
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onDestroy() {
        super.onDestroy()
        engineVision.close()
        bg.shutdown()
    }
}

