#include "communication/grpc_client.hpp"
#include "neuro_pipeline.pb.h"
#include <chrono>
#include <iostream>
#include <thread>

int main() {
    communication::GRPCClient::Config config;
    config.server_address = "localhost:50051";

    communication::GRPCClient client(config);

    std::cout << "[1/4] Connecting to server..." << std::endl;
    if (!client.Connect()) {
        std::cerr << "❌ Connection failed" << std::endl;
        return 1;
    }
    std::cout << "✅ Connected" << std::endl;

    std::cout << "[2/4] Sending detection result..." << std::endl;
    neuro_pipeline::DetectionResult result;
    result.set_frame_id(1);
    result.set_timestamp_us(
        std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());

    auto* box = result.add_boxes();
    box->set_class_name("person");
    box->set_confidence(0.95f);
    box->set_x_min(0.3f);
    box->set_y_min(0.4f);
    box->set_x_max(0.6f);
    box->set_y_max(0.8f);

    if (!client.StreamDetection(result)) {
        std::cerr << "❌ Send failed" << std::endl;
        return 1;
    }
    std::cout << "✅ Detection sent" << std::endl;

    std::cout << "[3/4] Testing health check..." << std::endl;
    if (!client.HealthCheck()) {
        std::cerr << "❌ Health check failed" << std::endl;
        return 1;
    }
    std::cout << "✅ Health check passed" << std::endl;

    std::cout << "[4/4] Disconnecting..." << std::endl;
    client.Disconnect();
    std::cout << "✅ Disconnected" << std::endl;

    std::cout << "\n========================================" << std::endl;
    std::cout << "  All tests passed" << std::endl;
    std::cout << "========================================" << std::endl;
    return 0;
}
