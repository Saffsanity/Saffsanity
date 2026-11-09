// Print the text inside any QR codes in an image, using macOS's built-in detector.
//   swift qr_read.swift image.png
import CoreImage
import Foundation

guard CommandLine.arguments.count == 2,
      let image = CIImage(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])),
      let detector = CIDetector(ofType: CIDetectorTypeQRCode, context: nil,
                                options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])
else {
    FileHandle.standardError.write("usage: swift qr_read.swift image.png\n".data(using: .utf8)!)
    exit(1)
}
for case let qr as CIQRCodeFeature in detector.features(in: image) {
    print(qr.messageString ?? "")
}
